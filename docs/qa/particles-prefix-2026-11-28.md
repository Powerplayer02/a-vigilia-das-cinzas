# Fase 5 — reduzir o custo da capacidade vazia

O controle comparável passou: delta livre de mediana **+0,1389 ms**, p95
**−0,0059 ms** contra a referência de CPU `8a245a4`. A candidata anterior
marcava +1,2860 ms. Não houve troca de regra, dano, cadência ou catálogo.
O alvo histórico absoluto continua fora da faixa; isso não é aceite integral
de release nem demonstra a causa do pico antigo.

## Diagnóstico e mudança

Não existem `Actor`, malhas com pesos ou deformação de vértices no jogo.
Os rigs são nós rígidos articulados com GLSL explícito. Hardware skinning
não acelera esse caminho de transforms. `setShaderAuto()` não foi acrescentado
como um interruptor de desempenho: [o recurso documentado](https://docs.panda3d.org/1.10/python/programming/shaders/shader-generator)
se aplica à animação de vértices.

Já há dois lotes e um buffer de vértices compartilhado; não há NodePath por
partícula. O LOD existente reduz emissões por distância. O diagnóstico isolado
sem GSG mostrou mediana de update de 1,0927 ms para 500 vivas/capacidade2.000,
contra0,51015 ms com capacidade500. Processar slots vazios era custo evitável.

O pool agora mantém o limite superior ocupado e simula/projeta somente esse
prefixo. Buracos internos continuam válidos; a cauda permanece transparente
e degenerada no ponto da região. Objetos, buffers, capacidade2.000, lifetime,
movimentos e RNG permanecem. Warmup restaura também esse limite superior.
Na repetição isolada, 500/2.000 caiu para0,62205 ms. O ensaio isolado de2.000
vivas variou no sentido contrário (1,9212→3,6585 ms); não se usa esse conjunto
sequencial para afirmar ganho geral ou custo de GPU.

## Quatro controles nativos

60 s por controle, warmup5 s, 1280×720, Custódio/20 inimigos, 500 partículas
constantes, áudio, bloqueio sintético por frame, sem PStats/cProfile/glFinish.
Todos tiveram zero minimizações e frames sem foco. Fonte candidata
`5c767c5b110befb0`; referência `c040c1317c82a595`.

| Caso | Mediana / p95 (ms) | FPS médio |
| --- | --- | --- |
| Referência cap60 | 16,6667 / 16,7331 | 59,95 |
| Candidata cap60 | 16,6666 / 16,7215 | 59,99 |
| Referência livre | 6,83035 / 11,1181 | 137,36 |
| Candidata livre | 6,9693 / 11,1122 | 136,03 |

O gate comparativo passou, inclusive no piso adicional de59,5 FPS.
O alvo absoluto3,665/7,0191 ms ±1 ms não passou e não foi removido.
2,188 ms citados no parecer eram um escopo inclusivo de animação/arma/feedback
na cena de2.000 partículas; o delta livre anterior veio da cena de500.
Esses números não podem ser subtraídos para obter tempo de GPU de partículas.

O novo estresse120 s encerrou sem relatório. O log permanece em
`artifacts/particles-opt-2026-11-28/coverage.log`; não há amostra válida dessa
execução. O teste anterior de29,414 ms permanece histórico, na fonte anterior.
O harness agora falha explicitamente se a janela fechar antes de concluir,
em vez de retornar sucesso sem dados. A repetição será separada da camada UI.

## Verificação e isolamento

830 testes locais passaram. A galeria nativa repetiu14 verificações, mantendo
snapshots e conexão dos buffers. A sincronia35/35 da revisão anterior não mudou.
O snapshot completo em `artifacts/particles-opt-2026-11-28/phase5-frozen/`
preserva o estado anterior ao onboarding para a próxima comparação.
[Dados e hashes](particles-prefix-2026-11-28.json).
