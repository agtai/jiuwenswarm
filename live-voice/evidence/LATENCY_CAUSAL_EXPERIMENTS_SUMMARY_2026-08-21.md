# Resumo dos experimentos causais de latência do Live Voice

Data: 2026-08-21

## Objetivo e limite

Este documento reúne as duas primeiras investigações causais de latência:

1. entrega das notificações P2 depois que o modelo termina;
2. detecção de fim de fala e finalização STT pelo Provider.

Elas foram executadas separadamente para atribuir a espera ao owner correto.
Seus tempos não devem ser somados como se formassem uma medição end-to-end. O
primeiro experimento não usa áudio ou Provider; o segundo termina no STT final
e não executa Agent, P2, TTS ou Browser.

Os registros exatos são:

- [resultado causal P2 bounded pull](P2_NOTIFICATION_BOUNDED_PULL_CAUSAL_RESULT_2026-08-21.md);
- [resultado causal VAD/EOT](VAD_EOT_CAUSAL_RESULT_2026-08-21.md).

## Leitura rápida

| Experimento | Pergunta | Resultado |
|---|---|---|
| P2 notification delivery | O `chat.final` fica esperando atrás de uma notificação por RPC? | Sim. Bounded pull reduziu o p50 em 90,0–92,9% e foi aceito no escopo causal P2 |
| VAD/EOT | Podemos substituir globalmente 1200 ms por 900 ou 800 ms? | Não. Ambos reduziram o tempo nos casos bem-sucedidos, mas preservaram somente 14/20 turns |

Assim, houve um ganho implementável no P2. No VAD houve ganho de tempo
potencial, mas não um ganho aceitável como constante global porque ele cortou
ou truncou fala.

## Termos estatísticos

- **Attempt:** uma execução independente da mesma configuração e fixture.
- **p50:** mediana; metade das amostras válidas terminou abaixo desse valor.
- **p95 nearest-rank:** menor amostra ordenada que cobre pelo menos 95% da
  população. Evidencia a cauda lenta melhor que apenas a média.
- **A1:** controle executado antes do candidato.
- **B/E:** configuração experimental.
- **A2:** repetição do controle original. A1 e A2 próximos reduzem o risco de
  atribuir variação de máquina/rede ao candidato.
- **Successful timing sample:** tentativa que passou identidade, ordem,
  integridade e cleanup. Uma fala truncada nunca recebe crédito por parecer
  rápida.

## Experimento 1 — transporte P2 bounded pull

### Problema medido

O caminho formal buscava somente uma notificação retida por RPC:

```text
modelo termina
  → notificações reasoning/delta ainda enfileiradas
  → Browser solicita nextNotification
  → recebe uma notificação
  → inicia outro RPC
  → ...
  → finalmente consome chat.final
```

Hongxing havia observado aproximadamente 64 posições restantes depois do fim
do modelo. Com cerca de 85 ms por ciclo Browser/RPC, isso explicava
aproximadamente 5,44 segundos de espera fora do Agent/modelo.

### O que significa o tempo P2

`model complete → final consumed` começa quando o Agent determinístico já
publicou toda a sequência, incluindo `chat.final`. Termina quando o owner Web
validou e consumiu a apresentação final correta.

Esse intervalo inclui:

- espera das notificações anteriores na fila;
- chamadas `nextNotification` necessárias;
- delay controlado de 85 ms por RPC;
- validação e consumo pelo owner Web.

Ele não inclui geração do modelo, STT, TTS, áudio ou playout. Portanto, mede
diretamente o atraso causado pelo protocolo de consumo P2 após o modelo estar
pronto.

### Método

- Fake Agent publica 10, 50 ou 100 notificações em ordem.
- A última é `chat.final`; todas as anteriores são observações
  `reasoning/delta`.
- Cada RPC recebe delay controlado de 85 ms.
- A1 e A2 usam o owner legado de uma notificação por RPC.
- B usa bounded pull de até 16 notificações, parando em qualquer barreira
  autoritativa como final, erro ou Task.
- Cada combinação executa cinco attempts.

Os números de RPC abaixo são o total das cinco tentativas. Por tentativa, o
owner antigo usa 10/50/100 RPCs; bounded pull usa 1/4/7.

### Tempos P2

| Notificações | A1 RPC / p50 / p95 | B RPC / p50 / p95 | A2 RPC / p50 / p95 |
|---:|---:|---:|---:|
| 10 | 50 / 864,293 / 873,600 ms | 5 / 85,823 / 91,008 ms | 50 / 860,659 / 867,540 ms |
| 50 | 250 / 4.348,227 / 4.351,440 ms | 20 / 343,704 / 349,175 ms | 250 / 4.305,376 / 4.343,331 ms |
| 100 | 500 / 8.658,478 / 8.700,760 ms | 35 / 615,209 / 617,248 ms | 500 / 8.643,205 / 8.681,116 ms |

| Notificações | Ganho p50 de B contra A1 / A2 | Ganho p95 de B contra A1 / A2 |
|---:|---:|---:|
| 10 | 90,070% / 90,028% | 89,582% / 89,510% |
| 50 | 92,096% / 92,017% | 91,976% / 91,961% |
| 100 | 92,895% / 92,882% | 92,906% / 92,890% |

A1, B e A2 passaram 15/15 attempts cada. Ordem, replay, final/error/Task e
todos os contadores de efeitos proibidos permaneceram corretos. O retorno de
A2 à curva original confirma que o ganho veio do bounded pull, e não de drift
do runner.

## Experimento 2 — VAD/EOT e finalização STT

### Problema medido

O caminho atual espera 1200 ms de silêncio para o server VAD concluir que o
usuário terminou. Diminuir esse valor pode responder antes, mas também pode
interpretar uma respiração ou pausa natural como fim definitivo do turn.

O experimento isolou:

```text
último frame de fala
  → silêncio observado pelo server VAD
  → SPEECH_STOPPED / EOT
  → transcrição final completa do Provider
```

### Definição de cada etapa

| Etapa | Início | Fim | O que representa |
|---|---|---|---|
| `final voiced frame → EOT` | instante agendado do último frame realmente falado | primeira observação tipada de `SPEECH_STOPPED` | espera principal do VAD mais transporte/observação do evento |
| `EOT → STT final` | `SPEECH_STOPPED` observado | evento tipado `FINAL` com transcript completo | finalização da transcrição pelo Provider e entrega ao adapter |
| `final voiced frame → STT final` | último frame falado | `FINAL` válido | soma operacional das duas etapas anteriores |
| pacing lateness | deadline monotônico de cada frame | envio efetivo do frame | atraso introduzido pelo próprio runner; serve como gate, não como latência do produto |

O **último frame falado** não é simplesmente o último sample diferente de zero.
O corpus usa o final da última janela de 10 ms cujo RMS excede 512, evitando
confundir ruído residual do celular com fala.

O **EOT** aqui é o evento do Provider observado pelo processo Python. Não é o
recebimento no Browser nem o submit ao Agent.

O **STT final** exige identidade correta, exatamente um turn e transcript
normalizado completo. Se o Provider encerra durante uma pausa e perde a parte
seguinte, a tentativa é `EARLY_EOT` ou `TRANSCRIPT_INCOMPLETE` e seus tempos não
entram nos percentis.

### Método

- Um WAV imutável foi dividido numa fronteira de baixa energia.
- A pausa original foi substituída por pausas totais exatas de 0, 300, 600 e
  1000 ms.
- O áudio PCM mono de 48 kHz foi enviado em frames contíguos de 20 ms e em
  tempo real ao `OpenAIStreamingSpeechProvider` existente.
- Sequência: A1/1200 → E1/900 → E2/800 → A2/1200.
- Cada configuração/caso executou cinco attempts formais, totalizando 80.

### Tempos agregados por configuração

Os percentis abaixo agrupam somente tentativas completas da configuração. Por
isso E1/E2 têm 14 amostras, enquanto A1/A2 têm 20.

| Configuração | Sucesso | Fala final → EOT p50 / p95 | EOT → STT final p50 / p95 | Fala final → STT final p50 / p95 |
|---|---:|---:|---:|---:|
| A1 / 1200 | 20/20 | 1.504,686 / 1.544,771 ms | 398,451 / 559,717 ms | 1.912,139 / 2.062,348 ms |
| E1 / 900 | 14/20 | 1.219,531 / 1.231,587 ms | 417,651 / 558,870 ms | 1.642,875 / 1.778,240 ms |
| E2 / 800 | 14/20 | 1.095,555 / 1.135,512 ms | 394,576 / 523,472 ms | 1.490,178 / 1.596,774 ms |
| A2 / 1200 | 20/20 | 1.504,093 / 1.568,416 ms | 400,308 / 561,132 ms | 1.915,885 / 2.064,958 ms |

### Integridade e EOT por pausa

| Pausa | A1 / 1200 sucesso; EOT p50/p95 | E1 / 900 sucesso; EOT p50/p95 | E2 / 800 sucesso; EOT p50/p95 | A2 / 1200 sucesso; EOT p50/p95 |
|---:|---:|---:|---:|---:|
| 0 ms | 5/5; 1.503,5 / 1.561,2 | 5/5; 1.220,3 / 1.223,2 | 5/5; 1.078,2 / 1.080,5 | 5/5; 1.500,4 / 1.545,8 |
| 300 ms | 5/5; 1.502,7 / 1.510,1 | 4/5; 1.199,3 / 1.231,4 | 4/5; 1.104,1 / 1.133,8 | 5/5; 1.498,3 / 1.568,4 |
| 600 ms | 5/5; 1.521,6 / 1.544,8 | 5/5; 1.219,7 / 1.231,6 | 5/5; 1.099,6 / 1.135,5 | 5/5; 1.520,9 / 1.524,9 |
| 1000 ms | 5/5; 1.501,4 / 1.516,7 | 0/5; — | 0/5; — | 5/5; 1.504,4 / 1.587,0 |

Os 12 failures dos thresholds menores foram dez `EARLY_EOT` e duas
`TRANSCRIPT_INCOMPLETE`. Pacing e cleanup passaram 80/80; `UNKNOWN` e
`INVALID` ficaram em zero. A redução observada nos casos válidos foi de cerca
de 280–425 ms, mas 900 e 800 ms foram rejeitados como defaults globais porque
cada um preservou somente 14/20 turns.

## Como os dois experimentos se encaixam no pipeline

| Parte do pipeline completo | Coberta? | Experimento / observação |
|---|---|---|
| Captura física no microfone | Não | Exige Browser/dispositivo |
| Última fala → EOT | Sim | VAD/EOT real-Provider |
| EOT → STT final | Sim | VAD/EOT real-Provider |
| Gateway submit → Agent/modelo | Não | Nenhum dos dois runners mede esta etapa |
| Execução Agent/modelo | Não | O P2 começa somente depois do modelo completo |
| Modelo completo → apresentação final consumida | Sim | P2 causal com transporte determinístico |
| Texto final → primeiro áudio TTS | Não | Próximo owner sugerido por Hongxing |
| Downlink → WebAudio → primeiro som audível | Não | Exige o caminho físico Browser |

Portanto, os resultados não dizem que a resposta completa ficou em 615 ms ou
1,49 segundo. Eles dizem que:

- o antigo transporte P2 podia adicionar até cerca de 8,66 segundos no caso
  sintético de 100 notificações, e bounded pull reduziu essa etapa para cerca
  de 615 ms;
- o threshold fixo de VAD domina aproximadamente 1,5 segundo do intervalo fala
  final → EOT no controle atual;
- reduzir globalmente o threshold compra 280–425 ms, mas quebra a integridade
  de pausas longas;
- geração Agent, TTS e Browser continuam fora dessas duas medições.

## Decisões e próximos owners

1. **P2 bounded pull: aceito no escopo causal.** Deve ser preservado e ainda
   receber confirmação física antes de crédito end-to-end.
2. **VAD fixo 900/800: rejeitado.** O default de 1200 ms permanece; uma próxima
   proposta precisa ser semântica/adaptativa e preservar os mesmos gates.
3. **EOT/STT settlement overlap:** pode ser investigado sem reduzir o threshold,
   separando Provider final pronto de settlement local completo sem enfraquecer
   ACK ou commit.
4. **TTS time-to-first-audio:** é o próximo grande bloco da ordem recomendada
   por Hongxing que ainda não possui este tipo de resultado causal fechado.
5. **Browser físico:** continua necessário antes de afirmar melhora percebida
   ou end-to-end, mas não bloqueia experimentos causais owner-specific.

## Fontes e limites

- [plano atual de otimização](../roadmap/LATENCY_OPTIMIZATION_PLAN_2026-08-18.md)
- [STATUS atual](../STATUS.md)
- [resultado P2](P2_NOTIFICATION_BOUNDED_PULL_CAUSAL_RESULT_2026-08-21.md)
- [resultado VAD/EOT](VAD_EOT_CAUSAL_RESULT_2026-08-21.md)

Áudio, transcripts, Provider item IDs, credenciais e relatórios raw permanecem
fora do Git. Este resumo não concede crédito de Browser, end-to-end,
product-readiness ou Production.
