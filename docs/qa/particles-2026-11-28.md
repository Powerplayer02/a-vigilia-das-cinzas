# Fase 5 — partículas, orçamento e medição

**Implementação entregue para revisão; aceite gráfico reprovado.** O estresse
final passou no teto e no limite de spikes, mas a comparação livre excedeu
o orçamento de mediana. A fase 6 não foi iniciada.

## Implementação

Um pool compartilhado por toda a cena, com teto obrigatório de **2.000**.
Objetos Particle, Geoms, arrays de vértices/índices e scratch NumPy são criados
no carregamento. Não se cria um nó, objeto de partícula ou buffer para cada
emissão/frame. Existem temporários escalares e wrappers Python; não se afirma
alocação zero do interpretador. Dois lotes: alpha e aditivo.

O LOD reduz a densidade das emissões a 12/24/40 m. A ambientação deixa até
256 posições reservadas para combate e reduz pedidos antes de esgotar o pool.
O teto vale também para bursts simultâneos e transições, sem pools auxiliares
que possam ultrapassá-lo. O limite de admissão de 500 é usado apenas nas
fixtures comparáveis; o jogo mantém capacidade 2.000.

Catálogo de 19 presets: sangue, brasas, faíscas, almas, level up, fase de chefe,
magia/cura e novos poeira, fumaça, chama, névoa, chuva, respingo, cinza, motas,
detritos, onda de Slam e onda de level up. O shader GLSL produz círculos suaves,
anéis, streaks e fragmentos sem atlas externo ou shader diferente por preset.

| Gatilho/área | Apresentação |
| --- | --- |
| Carne / metal / escudo | Sangue ou faíscas, pelo evento de dano |
| Fogo / parry | Brasas/fumaça ou faíscas |
| Roll / dash / slide | Poeira junto ao piso |
| Slam | Onda no ponto de contato e poeira, sem novo dano |
| Coleta / level up | Almas convergindo; burst e onda |
| Fogueiras | Chamas, brasas, fumaça e iluminação pulsante |
| Pântano | Névoa baixa, chuva leve e respingos |
| Ruínas | Poeira e detritos ocasionais |
| Forno | Chamas, faíscas e cinzas ascendentes |
| Catedral | Poeira suspensa e chamas nos pontos existentes |
| Pátio | Cinzas esparsas e fogo nos braseiros existentes |

O sistema dedicado `engine/particle_scene.py` recebe área/posições da composição.
Não importa world/model, não modifica física, HP, stats ou persistência.
Pausa congela simulação visual; uma volta após stall não despeja segundos de
emissões atrasadas. RNG é visual e separado do combate.
O personagem continua usando suas regras e timings anteriores, inclusive no
modo experimental OFF. O equilíbrio de chefes foi preservado.

## Preparo e desempenho do código

Todos os tipos/estados de blend existem desde o boot e participam do warmup
sob cobertura. Carga/transições preservam snapshots, RNG e timers de combate.
Fases tardias reutilizam shader/geometria/buffers já criados: o evento agenda
preparo no render normal do rugido, sem I/O, Shader.make ou novo passo de regra.
Premunge continua fora dos Geoms dinâmicos, para preservar referências/bounds.

O update escreve pelos buffers nativos, sem `.tobytes()` por quadro; grandes
operações NumPy usam scratch persistente. Índices só mudam quando a distribuição
alpha/aditiva muda. Bounds conservadores são obtidos dos centros/tamanhos já
avaliados e reutilizam uma caixa, evitando nova leitura nativa de cada vértice.
O teste confirma cobertura dos billboards rotacionados e dos anéis no chão.

A névoa usa a posição em espaço de vista, obtida por `p3d_ViewMatrix` no
vertex shader. A luz pulsante usa `osg_FrameTime` e um offset atualizado apenas
na inicialização/pausa/retomada. A posição da fogueira só muda quando a âncora
muda. Não se reinstalam inputs de câmera/relógio na raiz por frame. A galeria
nativa verifica mudança dos pixels, congelamento na pausa e identidade do
RenderState preservada. Não há parâmetros PTA neste caminho final.
Não há shader automático ou afirmação de compilação antecipada universal.

## Checkpoint anterior e comparação

A referência é a fase 4 com otimização de CPU publicada separadamente em
`8a245a4fce4aa1bd63adcf64f6d32e77ed789db2`, sem estes recursos de partículas.
O [checkpoint de 30 s](animation-cpu-checkpoint-2026-11-28.md) passou com nota
para o total inclusivo de arma/feedback: 2,3124/3,0442 ms; o escopo simples de
poses/views/mixer deu 1,1347/1,4886 ms. Mediana de frame limitada16,6673 ms.
[807 testes passaram em cada plataforma nesse commit](https://github.com/Powerplayer02/a-vigilia-das-cinzas/actions/runs/46133778907).

O protocolo da fase 5 usa fonte/harness comparáveis, quatro controles de60 s,
5 s de warmup e mais120 s com as seis famílias reais, jogador, todas as poses
do catálogo e três fases do Custódio, com2.000 partículas ativas. São fixtures
de apresentação sobre combate com HP elevado, não um playthrough de todas as
ações por inputs nem uma avaliação de dificuldade humana.

### Resultado final, sem escolher a melhor rodada

Os dois controles livres finais usam o mesmo harness e comando de bloqueio
reafirmado a cada frame. Ambos e o estresse tiveram **zero frames sem foco e
zero minimizações**. A referência congelada confere com os arquivos de
produção do commit de CPU, normalizando somente CRLF/LF. A fonte da candidata
tem fingerprint `2bd835ad82b2f925`, igual à galeria nativa final.

| Amostra | Duração | Mediana / p95 (ms) | Máximo (ms) |
| --- | --- | --- | --- |
| CPU anterior, 500 partículas, livre | 60,009 s | 6,7988 / 11,9597 | 22,903 |
| Fase 5, 500 partículas, livre | 60,009 s | 8,0848 / 12,6205 | 22,856 |
| Fase 5, 2.000 partículas, catálogo completo | 120,006 s | 11,5253 / 15,2597 | 29,414 |
| Fase 5, cap 60, controle anterior separado | 60,010 s | 16,6671 / 16,7641 | 62,168 |

A comparação livre final tem **+1,2860 ms de mediana e +0,6608 ms de p95**.
Reprova o limite de ±1 ms pela mediana. O par anterior a esta rodada tinha
passado (+0,7908/+0,7191 ms); ele continua arquivado e não substitui o resultado
final. O controle limitado foi feito na mesma fonte, antes do reforço do
harness de foco: não é um quarteto contemporâneo de controles. Sua mediana
passa em 16,7 ms; a média de 59,49 FPS reprova o requisito adicional de 59,5
do validador compartilhado. Esse requisito não foi removido para aprovar dados.

O estresse manteve exatamente 2.000 partículas em todos os 10.464 frames e
teve **zero frames acima de 50 ms**. Animação conservadora, incluindo arma e
feedback: **2,1875/2,9498 ms** de mediana/p95, aceita com nota de 2–4 ms.
O escopo simples deu 1,0537/1,4015 ms; partículas, 2,36425/3,2036 ms;
`_fixed_step`, 2,11145/2,9159 ms por passo (7.200 passos). Os escopos são
separados e não se somam como se fossem tempos exclusivos.

O alvo histórico absoluto **3,665/7,0191 ms ±1 ms também não foi atingido**.
Um controle atual com os arquivos reais da fase 3 marcou 4,4256/9,9675 ms:
o p95 histórico não foi reproduzido nem nessa fonte. Isso limita atribuição
causal, sem dispensar a régua. Não foi demonstrado que todo o delta seja do
ambiente, da GPU ou das partículas. Os dois gates finais permanecem vermelhos.

### Falhas e diagnóstico preservados

A primeira execução livre da candidata foi minimizada em328 frames: inválida.
A repetição válida confirmou regressão antes das otimizações finais:
9,03795/13,8396 ms contra6,2259/10,3828 ms da referência atual (mediana/p95).
Não se descartou a amostra válida para escolher um resultado melhor.

Rodadas posteriores perderam foco mesmo sem minimizar. Os relatórios antigos
podem conter `valid_sample: true` sob a regra anterior; o índice aplica também
o contador de foco e os identifica como inválidos hoje. O harness final espera
a janela selecionada, mantém o comando e os três validadores rejeitam perda
de foco. Nenhum intervalo bruto foi removido dos relatórios.

O primeiro estresse120 s já manteve2.000 partículas e zero minimizações,
com máximo32,362 ms e nenhum frame>50 ms. Ele antecede os últimos ajustes;
a versão final foi submetida novamente ao protocolo.
Ensaios curtos com contadores de estágios são diagnósticos, não baselines.

O contador separa `_fixed_step`, poses/views/mixer, arma/apresentação e
partículas/emitters. O total conservador soma pose lógica+apresentação externa;
não soma seus filhos novamente. Os tempos são de parede na thread do jogo,
incluem escalonamento e não são tempo exclusivo de CPU ou medição de GPU.

O diagnóstico separado por timer queries foi executado com suporte ativo e
glFinish OFF. Capturou203 frames GPU no conjunto e apenas9 correspondências
numéricas exatas com os marcadores Main da medição;194 ficaram fora da janela
correlacionada. Há lacunas, possível diferença de alinhamento dos contadores
e custo do profiler/transporte. Esses dados não qualificam FPS, não isolam
startup de forma definitiva e não demonstram a causa dos334,6945 ms históricos.
Dados brutos e os frames não correspondidos foram preservados.

## Verificação funcional

**827 testes locais passaram em 23,65 s**, preservando os 807 do checkpoint.
A galeria nativa
percorreu cinco áreas, dez capturas de ambientação/combate e quatro transições
de chefe. Todas preservaram snapshots, os90 passos de transição e conexão dos
buffers mutáveis ao grafo. O teste de luz confirmou atualização visível sem
troca do estado da raiz. Os35 pares de ataque/fase continuam dentro de±2passos.

O CI comum nas três plataformas verifica contratos, sem GPU. O workflowGPU
manual foi atualizado para a referência de CPU, o teto2.000 e contadores
separados. Uma falha da comparação não impede coletar o estresse; o job falha
ao final mantendo os dois pareceres. O runner dedicado continua sem
provisionamento nesta sessão.
Nenhum playtest humano, escuta ou certificação de release foi acrescentado.

[Índice de evidências e hashes](particles-2026-11-28.json). Relatórios locais
em `artifacts/particles/`; nenhuma fixture usa o banco do usuário.
