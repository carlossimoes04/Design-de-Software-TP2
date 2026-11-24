# Bairro Solar - Arquitetura

## 1. Arquitetura

### *User Stories*
As *User Stories* criadas foram as seguintes:
1. Como gestor, quero que o sistema calcule e registe o saldo no fecho de cada período de 15 minutos (sem contar duplicados), para acompanhar o balanço da comunidade.

2. Como gestor, quero que os valores que chegam depois de o período fechar fiquem registados para consulta futura, sem mexer nos saldos que já foram publicados, para saber sempre de onde vem cada número e garantir que os totais continuam certos.

3. Como membro, quero ser avisado quando um excedente começa e acaba, para poder aproveitar a energia renovável disponível.

4. Como gestor ou membro, quero ver num painel as mudanças de estado do excedente, para acompanhar facilmente quando a comunidade está a produzir em excesso.

5. Como gestor, quero que o sistema detete telhados a produzir muito menos do que os vizinhos da rua e descubra a causa (sombra, sujidade ou avaria), para evitar falsos alarmes e agir apenas quando necessário.

6. Como membro, quero enviar relatos em texto livre na app sobre o meu painel, para dar contexto sobre possíveis quebras de produção.

7. Como membro, quero ser avisado para limpar o painel quando a causa for sujidade (e não receber avisos em sombras temporárias), para manter o meu telhado a produzir bem.

8. Como gestor, quero que seja registado um pedido de intervenção quando a causa for avaria (ou quando a IA falhar/estiver em dúvida), para poder acionar técnicos externos fora do sistema.

### Características Arquiteturais
Tendo em conta a tabela da secção 14 (características operacionais) do guia de estudo da aula 3, as duas características arquiteturais principais consideradas foram:
1. **Recuperabilidade**: "Os valores passam por um gateway por prédio, com rede móvel instável, que os reenvia quando a rede volta, por vezes em duplicado.";
2. **Robustez**: "A resposta do modelo é validada (...). Se for inválida ou não chegar, aplica-se uma regra sem IA (...)."

Foram também identificadas outras características relevantes, como a *Segurança* contra *prompt injection*, a *Testabilidade* com um modelo falso e a *Extensibilidade* para novos consumidores. De acordo com as secções 2 e 3 do enunciado, o design também as garante, mas decidiu-se não lhes dar prioridade porque as duas mencionadas acima são as que definem a estrutura principal do sistema.

### Componentes

| Componente | Responsabilidade | Base de Dados | Subscreve | Publica |
| :--- | :--- | :--- | :--- | :--- |
| Simulador | Gera medições, relatos e fecho de períodos a partir de cenários (com atrasos e duplicados) | - (lê ficheiros) | - | `consumo.medido`, `producao.medida`, `periodo.encerrado`, `relato.recebido` |
| Serviço Operacional | Calcula saldo (ignorando duplicados), guarda atrasados para auditoria, deteta mudanças de excedente, deteta anomalias (≥ 40% abaixo de ≥ 3 vizinhos, salvo se a rua inteira baixar) e executa ações na consola | SQLite (`operacional.db`) | `consumo.medido`, `producao.medida`, `periodo.encerrado`, `anomalia.classificada` | `saldo.calculado`, `excedente.iniciado`, `excedente.terminado`, `producao.anomala` |
| Serviço de Triagem | Mantém vista local (CQRS), classifica anomalias (1 de cada vez) através de uma interface de modelo (real ou falso para testes), valida a resposta aplicando regra sem IA em caso de falha, e regista as decisões | SQLite (`triagem.db`) | `producao.medida`, `relato.recebido`, `producao.anomala` | `anomalia.classificada` |
| Aviso | Imprime avisos aos membros na consola quando um excedente começa ou acaba | - | `excedente.iniciado`, `excedente.terminado` | - (consola) |
| Painel | Atualiza o painel na consola com as mudanças de estado do excedente | - | `excedente.iniciado`, `excedente.terminado` | - (consola) |

Nota: os consumidores **Aviso** e **Painel** subscrevem os mesmos eventos através de filas independentes (`aviso` e `painel`) ligados ao mesmo *exchange* (`topic`) no **RabbitMQ**.

## 2. Eventos

### Catálogo

De acordo com o enunciado, os eventos de partida são:
| Evento | Produtor | Consumidores | Conteúdo |
| :--- | :--- | :--- | :--- |
| `consumo.medido` | Simulador | Serviço Operacional | `casa_id`, `periodo`, `potencia_media_kw` |
| `producao.medida` | Simulador | Serviço Operacional <br> Serviço de Triagem | `telhado_id`, `rua_id`, `periodo`, `potencia_media_kw` |
| `periodo.encerrado` | Simulador | Serviço Operacional | `periodo` |
| `saldo.calculado` | Serviço Operacional | - (registado) | `periodo`, `producao_total_kw`, `consumo_total_kw`, `saldo_kw` |
| `relato.recebido` | Simulador | Serviço de Triagem | `relato_id`, `telhado_id`, `periodo`, `texto` |
| `excedente.iniciado` | Serviço Operacional | Aviso, Painel | `periodo`, `saldo_kw` |
| `excedente.terminado` | Serviço Operacional | Aviso, Painel | `periodo`, `saldo_kw` |
| `producao.anomala` | Serviço Operacional | Serviço de Triagem | `telhado_id`, `rua_id`, `periodo`, `producao_kw`, `media_vizinhos_kw`, `num_vizinhos` |
| `anomalia.classificada` | Serviço de Triagem | Serviço Operacional | `telhado_id`, `periodo`, `causa` (`sombra` \| `sujidade` \| `avaria`), `justificacao` |

### Como se evita perder mensagens e processar o mesmo evento mais do que uma vez

#### Para prevenir a perda de mensagens, deve proteger-se os três pontos de falha no caminho:

$$ Produtor → Broker → Consumidor → Base\,de\,dados $$

1. **Produtor → Broker:** as filas e os *exchanges* ficam guardados em disco (`durable`) e os eventos também (`persistent`), para não desaparecerem se o RabbitMQ reiniciar. O produtor espera pela confirmação de receção do *broker* (*publisher confirms*) antes de avançar.
2. **Broker → Consumidor:** o consumidor usa confirmação manual (`ack` manual). Assim, o RabbitMQ só apaga o evento da fila quando o consumidor avisar que terminou; se o consumidor cair a meio, o evento volta a ser entregue.
3. **Consumidor → Base de dados:** o consumidor grava primeiro os dados na sua base SQLite e só depois envia o `ack` ao RabbitMQ. Se fizesse ao contrário e falhasse entre os dois passos, o evento perdia-se.

#### Para prevenir o processamento duplicado de um evento:

- Como os *gateways* reenviam medições repetidas e o RabbitMQ pode voltar a entregar um evento se o consumidor falhar antes do `ack`, os serviços têm de ser idempotentes (receber o mesmo evento duas vezes tem o mesmo efeito que recebê-lo uma vez):
    1. **Chave única por evento:** cada serviço identifica os eventos pela sua chave natural: `(casa_id, periodo)` nos consumos, `(telhado_id, periodo)` nas produções e anomalias, e `relato_id` nos relatos.
    2. **Verificação na base de dados:** antes de processar, o consumidor verifica na sua SQLite (com uma tabela de registo/restrição `UNIQUE`) se aquela chave já foi tratada. Se já existir, ignora o evento (não volta a somar no saldo nem a disparar triagem) e envia o `ack` para o retirar da fila.

## 3. Triagem

### O que o modelo recebe

Quando recebe `producao.anomala`, o Serviço de Triagem lê apenas a sua vista local em SQLite (CQRS), sem pedir dados a mais nenhum serviço, e monta o pedido para o modelo em duas partes:

- No *system prompt* ficam as regras fixas: 
    1. O modelo atua como classificador com três causas possíveis (`sombra`, `sujidade` ou `avaria`) e tem de responder apenas em JSON no formato `{"causa": "sombra" | "sujidade" | "avaria", "justificacao": "..."}`;
    2. Também fica explícito que os relatos dos moradores são apenas dados a analisar e nunca instruções a seguir, para impedir tentativas de *prompt injection*.
    
- No *user prompt* são enviados os dados da anomalia:
    1. A produção do telhado nos últimos 4 períodos (última hora);
    2. A produção dos vizinhos da mesma rua no período e a respetiva média simples;
    3. Os relatos recentes desse telhado isolados entre `<relatos_morador>...</relatos_morador>`.

Antes de aceitar a resposta, o serviço valida-a tendo em conta o esquema JSON esperado. Tudo o que entra e sai do modelo (pedido, resposta bruta, causa final e se veio da `ia` ou de `fallback`) fica guardado na tabela `triagem_registo`. Para os testes e *evals* correrem sem chamar a API real, o modelo fica atrás da interface `TriageModel`, que tem a implementação falsa `FakeTriageModel`.

### A regra sem IA

Quando o modelo falha, demora demais ou devolve uma resposta fora do formato JSON esperado, o Serviço de Triagem passa para uma regra simples baseada apenas nos números de produção, ignorando o texto dos relatos dos moradores:
1. Se a produção atual caiu para perto de zero (≤ 10% da média dos vizinhos), marca como `avaria`;
2. Se foi descendo de forma gradual nos últimos 4 períodos, mantendo-se acima de 10% da média dos vizinhos, marca como `sujidade`;
3. Se faltar histórico, houver uma queda súbita sem contexto claro ou existir qualquer dúvida, marca como `avaria`.

A justificação enviada explica que a decisão veio da regra sem IA, e o registo fica guardado na tabela `triagem_registo` com origem `fallback`.

### O que correu mal com o modelo real

## 4. Decisões

### Porquê EDA e o que se perde

### Porque chega a topologia *broker* e quando seria preciso um *mediator*

### Como é que o sistema funciona quando a IA falha
