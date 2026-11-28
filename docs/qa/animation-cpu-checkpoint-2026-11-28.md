# Fase 4 — checkpoint de CPU e cap 60

O checkpoint passou **com nota para o custo inclusivo**, conforme o parecer
mais recente: mediana entre 2 e 4 ms aceitável, p95 até 4 ms. Uncapped e
spikes em 120 s foram transferidos para a comparação da fase 5 pelo usuário.
Não há certificação de lançamento nem explicação nova para o pico histórico.

Cena nativa visível, 30 s após 5 s de warmup, cap 60, 1280×720, Custódio fase 3,
20 inimigos com as seis famílias, 500 partículas e áudio ON. Roblox encerrado;
nenhum ensaio concorrente. PStats, timer queries e glFinish desligados.
São fixtures com HP elevado para manter combate, sem playtest humano.

## Falha preservada e otimização

Primeira fonte: fase 4 publicada (88d2d991), sem partículas da fase 5.
Mediana de poses/view/mixer 1,78485 ms; p95 4,2325 ms: **falhou no p95**.
Frame limitado: mediana 16,67965 ms, p95 28,0903 ms, zero minimizações.
A amostra não foi descartada para escolher um número melhor.

O contador apontou custo relevante na avaliação autoritativa de poses.
Foi reduzida a criação de Vec3 temporários, reutilizando somente pontos locais
imutáveis; mapeamentos e volumes mundiais continuam próprios de cada avaliação.
Arma e braços deixam de reaplicar transforms quando o resultado permanece
igual; a mudança do transform mundial invalida o cache do braço.

Comparação exata de 300 casos com a função anterior preservou todos os pontos
e raios. Quinze fixtures de coordenadas anteriores e regressões de cache fazem
parte da suíte. Sincronia de 35 ataques/fases continua dentro de dois passos.
Dano, janelas, regras, AST do passo fixo e tabelas dos chefes não mudaram.

## Reteste de 30 s

| Escopo medido | Mediana ms | p95 ms |
| --- | ---: | ---: |
| Poses autoritativas + views + mixer/transforms | 1,1347 | 1,4886 |
| Total conservador: poses + apresentação completa de combate, incluindo arma/feedback | 2,3124 | 3,0442 |
| `_fixed_step`, por passo lógico | 2,15855 | 2,9509 |
| Pool/buffers das 500 partículas anteriores, por render | 0,8201 | 1,1410 |
| Intervalo de frame com cap 60 | 16,6673 | 16,7813 |

1795 renders e 1800 passos lógicos, zero frames minimizados. O limite de
16,7 ms aplicado ao cap é o da **mediana**; o p95 é informado, não ocultado.
O total conservador soma dois escopos não sobrepostos: pose lógica e
`_draw_combat` completo. Não soma os subescopos view/mixer/arma novamente.
O orçamento simples ficou abaixo de 2 ms; o total inclusivo fica registrado
como aceito com nota, sem excluir silenciosamente a sincronização da arma.
São contadores de tempo decorrido na thread do jogo, incluindo escalonamento
do SO; não são timers de GPU nem tempo exclusivo de execução da CPU.

O reteste usa uma cópia da fase 4 com **somente** a otimização de poses e
transforms, mais o contador atualizado. O shader/pool/ambientes da fase 5
ficaram fora. Essa fonte é a referência para separar o custo das partículas.
O contador também observa partículas/emitters separadamente quando disponíveis.

## Evidências

[Índice e hashes](animation-cpu-checkpoint-2026-11-28.json) registra amostras,
fontes e gate. Relatórios locais completos preservam todos os tempos por frame
em `artifacts/particles/phase4-checkpoint.json` e
`artifacts/particles/phase4-optimized-checkpoint.json`.
`tools/check_animation_checkpoint.py` rejeita amostras curtas, minimizadas,
instrumentadas ou sem os contadores de animação/passo fixo.

A escolha anterior “GPU depois” e a nova liberação do checkpoint são decisões
em momentos distintos. Este relatório segue a mais recente e não reescreve
os registros históricos. Partículas também têm custo de CPU; seus contadores
separados evitam atribuir toda a diferença futura ao trabalho da GPU.
