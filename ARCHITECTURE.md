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
As duas características arquiteturais principais consideradas foram:
1. **Recuperabilidade**: "Os valores passam por um gateway por prédio, com rede móvel instável, que os reenvia quando a rede volta, por vezes em duplicado.";
2. **Robustez**: "A resposta do modelo é validada (...). Se for inválida ou não chegar, aplica-se uma regra sem IA (...)."

Foram também identificadas outras características relevantes, como a *Segurança* contra *prompt injection*, a *Testabilidade* com um modelo falso e a *Extensibilidade* de novos utilizadores. De acordo com as secções 2 e 3 do enunciado, o design também as garante, mas decidiu-se não lhes dar prioridade porque as duas mencionadas acima são as que definem a estrutura principal do sistema.

### Componentes

| Componente | Base de Dados | Subscreve | Publica |
| :--- | :--- | :--- | :--- |
| Simulador | - (lê ficheiros) | - | `consumo.medido`, `producao.medida`, `periodo.encerrado`, `relato.recebido` |
| Serviço Operacional | SQLite (`operacional.db`) | `consumo.medido`, `producao.medida`, `periodo.encerrado`, `anomalia.classificada` | `saldo.calculado`, `excedente.iniciado`, `excedente.terminado`, `producao.anomala` |
| Aviso | - | `excedente.iniciado`, `excedente.terminado` | - (consola) |
| Painel | - | `excedente.iniciado`, `excedente.terminado` | - (consola) |
| Serviço de Triagem | SQLite (`triagem.db`) | `producao.medida`, `relato.recebido`, `producao.anomala` | `anomalia.classificada` |

## 2. Eventos

### Catálogo

### Como se evita perder mensagens e processar o mesmo evento mais do que uma vez

## 3. Triagem

### O que o modelo recebe

### A regra sem IA

### O que correu mal com o modelo real

## 4. Decisões

### Porquê EDA e o que se perde

### Porque chega a topologia *broker* e quando seria preciso um *mediator*

### Como é que o sistema funciona quando a IA falha
