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

## 3. Triagem

### O que o modelo recebe

### A regra sem IA

### O que correu mal com o modelo real

## 4. Decisões

### Porquê EDA e o que se perde

### Porque chega a topologia *broker* e quando seria preciso um *mediator*

### Como é que o sistema funciona quando a IA falha
