# Fechamento da 1.0 — Etapa 5.5

Estado em 28/11/2026: fase 5 de partículas implementada para revisão, com
827 testes locais. Checkpoint de CPU da fase 4 medido e aprovado com nota;
comparação gráfica final reprovada pela mediana livre e alvo histórico.
Estresse de 120 s/2.000 partículas sem frame acima de 50 ms. Release ainda
não certificada, fase 6 não iniciada; avaliação humana e comparação ON/OFF
dos chefes permanecem pendentes. As seções antigas preservam a cronologia.
[Resultados atuais e falhas preservadas](docs/qa/particles-2026-11-28.md).

| Verificação | Estado |
| --- | --- |
| Testes locais de regras e contratos | 827 passaram no Windows; os 807 do checkpoint de CPU preservados |
| Fechar a janela sem salvar | Corrigido e verificado por Alt+F4 real: zero commits no fechamento |
| Checkpoint coberto por preto antes do commit | Verificado por leitura do frame apresentado |
| SQLite | WAL, synchronous=NORMAL (1), estado anterior preservado após fechar |
| Repositório | Powerplayer02/a-vigilia-das-cinzas |
| CI remoto Linux/macOS/Windows | Checkpoint separado aprovado: [807 por plataforma](https://github.com/Powerplayer02/a-vigilia-das-cinzas/actions/runs/46133778907); [execuções da camada atual](https://github.com/Powerplayer02/a-vigilia-das-cinzas/actions/workflows/tests.yml) |
| Três desfechos a partir de saves anteriores ao chefe final | Aprovado: três fixtures versionadas, combate/epílogo/pós-créditos; repetido com Bullet/UI nativos |
| Campanha com números de produção | Percurso principal e final Transformar concluídos por comandos do agente; não é avaliação humana |
| Comparação controlada de desempenho entre fases do chefe final | Pendente; não bloqueia release |
| Picos nativos de renderização | 18 capturas triadas; causa nativa não identificada. Quarentena histórica preservada |

O pico anterior de 333,681 ms era um commit iniciado por `request_quit`.
Esse caminho foi removido. Checkpoints, transições explícitas, desfecho e
pós-créditos continuam salvando; fechar a janela descarta alterações ainda
não gravadas. Uma transição de menu com falha de escrita conserva a sessão
e mostra o erro. O teste nativo local consta em `artifacts/5.5/shutdown.json`;
esses diagnósticos locais não são incluídos no repositório.

A 1.0 tem como alvo **teclado e mouse**. Gamepad permanece experimental,
fora dos recursos validados, conforme decisão do usuário. Os testes
simulados existentes não substituem um controle físico.

Os três desfechos compartilham o predicado de vitória sobre o chefe final
e a escolha confirmada no altar. Não existem predicados de quests de NPC
ocultos. A matriz nova parte de três bancos independentes anteriores ao chefe,
com HP de produção e nenhuma decisão antecipada. Depois de entrar na névoa,
o helper reduz o chefe a 1 HP para o golpe final real. Isso fecha o fluxo
funcional e a persistência; não substitui o playthrough de dificuldade.

O QA 5.4 utilizou HP, precondições e teleporte sintéticos declarados.
Ele valida o fluxo, mas não certifica tempo de combate, dificuldade ou
balanceamento. Não foram realizados três playthroughs manuais completos.

O plano antigo de mini-chefes e novas expansões foi substituído pelo
fechamento de release. Sentinela Oca e Viúva das Cinzas ficam fora da 1.0.
Nenhuma tag ou release 1.0 deve ser criada enquanto os bloqueios persistirem.

## Evidência do CI

Primeira publicação: commit `3205226e685077e31474bf1fef233069703a266a`.
O GitHub Actions executou os 306 testes em Linux (5,72 s), macOS ARM64
(6,28 s) e Windows (22,91 s), todos aprovados. Houve dois avisos sobre
propriedades personalizadas no relatório JUnit xunit2; a configuração passa
a usar xunit1 para conservar essas propriedades de migração.
Esses tempos são do pytest, sem incluir preparação e instalação.
O resumo verificável está em [docs/qa/ci-2026-11-24.json](docs/qa/ci-2026-11-24.json).

O pacote de 25/11/2026 preservou esses 306 testes e acrescentou 48.
**354 passaram em cada plataforma** no commit `ae294d58bc4563349f669820a90a48cb559af118`.
Evidência em [docs/qa/ci-2026-11-25.json](docs/qa/ci-2026-11-25.json).

## Movimento Ágil — primeira etapa

Solicitado depois do recorte de fechamento: Dash + Slide, OFF por padrão,
save por personagem e testes com physics fake e Bullet sem janela. O loop
fixo permaneceu idêntico. HP, dano, resistências e IA de chefes não mudaram.
Wall jump/Slam foram aprovados e entregues na etapa 2. Momentum geral,
coyote time e jump buffer foram aprovados e entregues na etapa 3.

A matriz manual OFF/ON dos chefes ainda não foi jogada. O modo continua
experimental; nenhuma avaliação de trivialização foi fabricada. O template
fica em `data/balance_templates/playthrough.md` e os registros locais em
`artifacts/balance/`. Medições OFF estão em `docs/qa/agile-off-performance.json`:
a mediana final foi 207,99 FPS contra 192,25 no controle anterior (+8,2%),
sem queda observada na mediana. Isso **não certifica equivalência ±5%**:
o código antigo variou de 139,20 a 199,10 FPS ao longo da sessão. Os três
ensaios finais válidos tiveram 1% low mínimo de 92,25; uma execução
minimizada foi invalidada e preservada. A série anterior inclui amostras
abaixo de 55 nas duas versões. Não foi estabelecida uma melhora causal.

A build final `0edc4fe38b5082dd` também passou por 10 s de carga com o
flight recorder ativo: sem pico acima de 200 ms, sem erro de captura e sem
quarentena. Esses FPS instrumentados não entram no baseline de desempenho.

## Etapa 2 e régua corrigida

Wall cling por 24 passos, salto para longe da parede e Slam de 18 m/s,
área de 2,5 m e recuperação de oito passos. O Slam publica evento puro;
o combate resolve sua fila de áreas depois da física, compartilhando o
resolvedor existente. O controle de movimento não ganhou import de combate.

As 354 regressões foram preservadas; 37 testes novos cobrem parede,
motor vertical, persistência, vulnerabilidade, AoE mockado e arquitetura.
O percurso nativo repetiu save/load no cling, na descida e após o impacto,
com lock-on preservado e sem dano repetido, incluindo queda diretamente
sobre o manequim e colisão na borda da cápsula. Build `d8f1c0ad3c23d5af`,
gravador ativo: sem picos acima de 200 ms, sem erro e sem quarentena.

Os 391 testes passaram também no CI de Linux, macOS e Windows. Contagens
por job e commit em `docs/qa/stage2-ci-2026-11-25.json`.

A exigência de ±5% de FPS foi retirada pelo usuário. A régua vigente usa
60 s, clock limitado a 60 Hz, mediana e p95 em ms; OFF deve ficar até
+1,0 ms da mediana pré-Ultrakill. Checkpoint: **16,6665 / 16,7601 ms**;
etapa 1 OFF: **16,6646 / 16,7232 ms**; etapa 2 OFF: **16,6651 / 16,7184 ms**
(mediana / p95). Diferença final da mediana: **−0,0014 ms**, aprovada.
Intervalos brutos em `docs/qa/frame-time-limited-2026-11-25.json`.

Balance OFF continua como próximo QA. Balance ON/OFF dos chefes vem depois
do OFF, sem misturar tuning de tabelas e mobilidade. A campanha manual ainda
não foi realizada e segue bloqueando o lançamento.

## Etapa 3 — momentum, coyote e buffer

Opção A implementada: `dash_attack` e `slide_attack` são entradas próprias
no moveset, com fatores no pacote de dano/poise; a fórmula de dano e sua
assinatura continuam idênticas. Nenhum import de combate foi acrescentado
em `player/`. Cling zera impulso horizontal; roll usa seu perfil original,
sem restaurar momentum ao sair. Críticos mantêm a pose estacionária anterior.

Momentum dura 24 passos, coyote e buffer aceitam seis passos. A suíte tem
**438 testes**, incluindo **47 novos**, com os limites 1/24/25/30 para ataque,
6/7 para salto, janelas simultâneas, compatibilidade com save anterior e
snapshot sem reiniciar timers e descarte de impulso expirado de saves antigos.
O percurso nativo `6b7f72854807d0ce` repetiu
coyote no sexto passo após reload, salto enfileirado na aterrissagem e
cancelamento por roll: sem pico acima de 200 ms, erro de captura ou quarentena.
Dash/slide, wall jump/Slam e os três desfechos também passaram novamente.

Os 438 testes passaram no CI de Linux, macOS e Windows. Resultados por job
e commit em `docs/qa/stage3-ci-2026-11-25.json`.

O protocolo agora mede capped e uncapped. No chefe final fase 3 com 20
inimigos e 500 partículas, 60 s: **252,80 FPS sem cap**, mediana/p95
**3,3827 / 6,6347 ms**; checkpoint repetido **240,63 FPS**, **3,4218 / 7,2286 ms**.
Resultado dentro da faixa histórica de 214–260 FPS; diferença de mediana
**−0,0391 ms**. Com cap de 60 Hz: **16,6646 / 16,7629 ms**, aprovado.
Capped verifica a meta; não demonstra overhead zero. Um par de execuções
uncapped não demonstra equivalência causal. Evidência versionada em
`docs/qa/stage3-frame-time-2026-11-25.json` e `docs/qa/stage3-native-2026-11-25.json`.

A etapa 3 foi executada antes da campanha manual OFF. A pendência não foi
substituída por smoke tests: tentativas, dificuldade percebida e calibração
de stamina ainda não foram medidas em partida. Nenhum HP/dano/resistência
de chefe foi ajustado. Balance OFF precede a comparação ON/OFF e continua
bloqueando a certificação do lançamento.


## Atualização de 26/11 — campanha OFF e música

Campanha OFF: Vigia, 9 tentativas / 503,359s; Abadessa, 6 / 166,465s;
Custódio, 1 / 247,576s. Final Transformar e créditos vistos persistidos em
save real. É um percurso conduzido pelo agente, não uma avaliação humana
nem exploração completa. O Custódio supera a referência de 210s.

A pedido do usuário, somente o HP do Vigia caiu 15% (3.200 → 2.720).
Rechecagem com Cavaleiro novo, nível 1 e espada +0: 177,608s, uma tentativa,
162,312/188 HP restantes. A política já tinha aprendizado; a diferença não
isola o efeito do HP. Abadessa, Custódio, fórmulas, timings, IA e passo fixo
preservados. Descanso preserva almas e mancha pela decisão mais recente.
Ver [relatório OFF](docs/qa/balance-off-2026-11-26.md).
[CI do balanceamento](https://github.com/Powerplayer02/a-vigilia-das-cinzas/actions/runs/45899901886).

Fase 1: 17 faixas originais; cinco ambientes de 96s, sete variações de
chefe de 96s, menu de 30s, três finais de 60s e pós-créditos de 30s.
Gerador NumPy + wave, cache WAV reparável no boot, sem geração por quadro.
Catálogo de 245.549.548 bytes. Medidor independente: −18 LUFS, com erro
máximo de 0,0003 LU. Crossfade por relógio real, névoa, fases, vitória,
redução de 6dB nas opções e finais sem loop. Mixer real validado em fixture
de apresentação separada da campanha. [Documentação](docs/audio_visual.md).

[466 testes nas três plataformas](https://github.com/Powerplayer02/a-vigilia-das-cinzas/actions/runs/45903934895),
incluindo hash PCM determinístico. Logs: Ubuntu, 466 / 10,46s; macOS,
466 / 5,40s; Windows, 466 / 22,38s.

60s por amostra, 5s de warmup, 1280×720 médio, Custódio fase 3 + 20 comuns +
500 partículas, janela nativa, sem cProfile ou minimização:

| Música | Cap | Mediana ms | p95 ms | FPS médio | 1% low |
| --- | --- | ---: | ---: | ---: | ---: |
| OFF | 60Hz | 16,6645 | 16,7313 | 59,98 | 55,91 |
| ON | 60Hz | 16,6640 | 16,7602 | 59,97 | 55,05 |
| OFF | Livre | 3,2583 | 6,5740 | 254,37 | 106,24 |
| ON | Livre | 3,2771 | 6,5854 | 253,29 | 101,65 |

Delta ON−OFF sem cap: +0,0188ms, dentro de +1ms. Não prova melhoria causal
ou eliminação dos picos históricos. Amostras minimizadas e uma sobreposição
acidental entre execuções foram invalidadas, preservadas e repetidas.
[Dados e hashes](docs/qa/music-performance-2026-11-26.json).

SFX novos e demais fases audiovisuais aguardam confirmação. A comparação
ON/OFF da mobilidade ainda está pendente. Nenhuma tag de release 1.0 foi
criada. Gamepad continua fora dos recursos validados.


## Atualização de 27/11 — efeitos e Custódio

106 efeitos e 93 presets, geração original NumPy + wave, variantes de armas,
feedback de condições/UI/magia e superfícies. Grupos de ganho separados:
combate 1,0; interface 0,9; ambiente 0,6; música 0,7. Duas vozes de UI ficam
protegidas; teste de saturação com oito vozes passou no mixer real. Soma PCM
com oito efeitos + música e sliders em 100%: pico −8,7261dBFS, sem recorte.
Maior pico individual: −4,0001dBFS. Não é avaliação auditiva.

Custódio final: HP 4.700, dano +10%, aproximação mais agressiva e pausas/
cooldowns menores. Windups, janelas de parry e fórmulas preservados.
Reteste completo: 200,167913s, 175,293/230HP. Pilotos minimizado/interrompido
foram invalidados e preservados. A condução é experiente e instrumentada;
nenhuma certificação de dificuldade humana é inferida dessa vitória.

O pico foi REPRODUZIDO: 334,6945ms em combate, fase 2, sem minimização;
313ms em renderFrame, 20,75ms em Game.frame. Sem GC registrado ou commit
SQLite na pilha desse quadro. Causa nativa em aberto, quarentena preservada.
O teste nativo de oito vozes não adicionou novos picos; herdou a quarentena.
Não eliminar I/O/SQLite/GC/shader das hipóteses históricas sem evidência.

700 testes passaram nas três plataformas. Dados em docs/qa/sfx-ci-2026-11-26.json.
Comparação de mobilidade ON/OFF e avaliação humana seguem pendentes.
Sprites/animações/partículas permanecem para fases futuras.


Medições finais dos SFX, todas com música ON, sem minimização:

| Efeitos | Cap | Mediana ms | p95 ms | FPS médio | 1% low |
| --- | --- | ---: | ---: | ---: | ---: |
| OFF | 60Hz | 16,6644 | 16,7348 | 60,01 | 59,37 |
| ON | 60Hz | 16,6653 | 16,7159 | 60,00 | 57,99 |
| OFF | Livre | 3,4393 | 6,4992 | 248,79 | 108,89 |
| ON | Livre | 3,5101 | 6,7743 | 241,36 | 102,14 |

Delta livre +0,0708ms; margem de ±0,5ms atendida. A amostra atual usa a
mesma tabela de chefe nas duas condições, separada da comparação histórica.
[Brutos e hashes](docs/qa/sfx-performance-2026-11-27.json).

## Fase 3 — interface validada, lançamento pendente

Atlas original de 36 células, 1024²/11 mipmaps, paleta única, fonte compartilhada,
HUD/menus/inventário/mapa integrados, fallback com assets vazios e escala até150%.
26 estados em720p/1080p/1440p e emassets vazios720p: sem transbordamento nas
medições de texto; slider150% e HUD ampliado conferidos em1440p.
712 testes locais passaram (17,90s), incluindo os700 anteriores.
Relatório: `docs/qa/sprites-ui-2026-11-27.json`.

Após remover o centro transparente das molduras e usar o mesmo programa de
medição/seed37 nas duas revisões, o gate passou: mediana cap60 16,6656ms,
delta livre de mediana +0,1473ms e de p95 +0,2231ms. Sem minimização nas quatro
execuções60s/5s-warmup. A primeira comparação havia falhado no p95 e foi
preservada, assim como controles minimizados/interrompidos, sem aproveitá-los
como aprovação. `docs/qa/sprites-performance-2026-11-27.json`.

O CI comum roda testes, não FPS. O novo workflow manual/reutilizável de
pré-release exige runnerGPU Windows interativo com etiqueta `vigilia-gpu`;
ele ainda não foi provisionado/executado nesta sessão. Não certificar o FPS
por um runner de software compartilhado.

Investigação do pico: a chamadaC++ `renderFrame` domina a captura antiga;
não há evidência suficiente para aplicar um fix específico de shader/textura/GC.
Novos contadores de recursos antes/depois do render e teste de retenção foram
adicionados apenas ao modo de diagnóstico. Uma execução separada60s teve
máximo31,277ms, sem reproduzir334,6945ms. Não é prova de correção.
**Pico nativo sem causa, dificuldade humana e escuta humana continuam pendentes.**
Fase4 e lançamento não liberados por esta entrega. Custódio mantém sua tabela.
Detalhes: `docs/qa/render-investigation-2026-11-27.md`.

### Decisão editorial — balanceamento beta

Escolha explícita: **(c), beta com feedback**. Não se declara balance OFF
concluído nem se prevê número de tentativas humanas a partir de um agente.
Mantêm-se as tabelas atuais, sem apresentar o Custódio como deliberadamente
fácil/acessível. O formulário `.github/ISSUE_TEMPLATE/balance.yml` coleta
tentativas, equipamento, ritmo e engasgos, separando partida humana de agente.
Isso não publica um release nem remove o bloqueio de renderização existente.

### Diagnóstico nativo e preparação inicial

PStats nativo1.10.16 capturado em três percursos completos com save pré-chefe,
cache Panda isolado e um controle gl-finish. Os maiores Main recebidos foram
552,660 / 259,201 / 392,100ms; todos antes de o chefe ficar ativo. Durante
chefe ativo, máximos recebidos33,051 /63,845 /122,711ms. Há lacunas de entrega
e custo do profiler; não são resultados de FPS nem repetição do pico histórico.
O `.frame.pstats` antigo é cProfile, sem barras nativas reconstruíveis.

Boot agora submete recursos já construídos sob cobertura preta, sem rodar
simulação. Teste nativo65,8441ms, snapshot preservado. A medida é defensiva;
assets ainda não criados não são cobertos. 716 testes locais passaram.
Detalhes, limitações e evidências: `docs/qa/render-investigation-2026-11-27.md`.
O pico de combate continua sem causa; fase4 permanece pendente.

## Fase 4 — implementação para revisão, aceite de GPU pendente

O usuário liberou o início das animações, mantendo a causa histórica aberta.
O mixer agora apresenta jogador, seis perfis comuns e os três chefes, incluindo
transições2/3 e variantes dos ataques existentes. São99 entradas de pose,
incluindo windup/active/recovery; não são99 modelos, shaders ou movimentos novos.
O passo fixo e as tabelas de chefes permanecem iguais à revisão6d079709.

Carregamento prepara os rigs, o frasco e os dois estados do pool de partículas
sob cobertura, preservando snapshot/transforms/RNG visual. Na transição, o
evento enfileira recursos existentes; o render normal consome a fila sem
rodar outro passo de combate. Testes nativos dos três chefes preservaram os
90 passos de transição; a fila de preparação do Panda foi consumida no teste.

A comparação de GPU não foi aceita: houve um controle livre minimizado e
atividade concorrente de outro jogo. A primeira amostra limitada válida
também não atingiu a média anterior de59,5FPS. Não se atribui essa diferença
inteira ao ambiente ou ao código sem repetir o controle. Houve alterações
posteriores para evitar setters redundantes, ainda sem benchmark final.
O usuário escolheu **deixar a medição final para depois**. Não houve nova
medição de FPS após essa decisão. O workflowGPU foi preparado, não executado.

Política de balanceamento: beta com feedback. Custódio4.700HP, dano+10% e
cadência atual preservados; vitória completa#1 do agente com175,293/230HP,
em200,167913s. Vigia2.720HP após redução15%. Esses resultados não medem
dificuldade humana, leitura dos telegraphs ou pressão percebida.
O feedback deve orientar patches de HP/dano/cadência, inclusive a curva entre
Vigia e Custódio, após partidas humanas. O formulário é o canal de calibração;
patches de balanceamento pós-lançamento fazem parte desta política beta.
Nenhum buff adicional foi aplicado sem novos dados.

O pico histórico e a abertura preta não foram atribuídos a first-use. Esta
última já ocorreu com o aquecimento anterior ativo e não se repetiu nos dois
controles seguintes; fica registrada, sem nova perseguição nesta fase.
Não há certificação de release1.0 nem de desempenho nesta entrega.
Relatório: `docs/qa/animations-2026-11-27.md`.

### Revisão da fase 4 — sincronia corrigida; desempenho ainda pendente

Os 35 pares de ataque/fase testados passaram na tolerância de ±2 passos.
Antes, o pico corporal podia atrasar 28 passos; agora antecede a primeira
ativação em um passo (16,67 ms), respeitando a ordem real de combate/render.
São 29 pares presentes nos movesets mais seis definições extras verificadas
na fase 1; os chefes existentes têm duas, duas e três fases respectivamente.
Não foram criados ataques para cumprir uma contagem artificial.
As armas permanecem alinhadas aos pontos autoritativos durante contato.
Dano, AttackDefinitions, tabelas dos chefes e passo fixo não mudaram.

Panda3D 1.10.16: `premunge_scene` prepara as geometrias estáticas e UI;
`prepare_scene` e os renders sob cobertura também incluem os buffers dinâmicos.
O caminho de partículas preserva suas referências de Geom/vertices/índices;
teste nativo verificou atualização dos dados no grafo após loading/transições.
Snapshots, RNG e os 90 passos de transição do chefe foram preservados.
Isso amplia a preparação; não demonstra a causa ou a eliminação do pico antigo.

O usuário escolheu “Faça a sincronia e o preparo; GPU depois”. Nenhum novo
benchmark de FPS/GPU foi executado após essa escolha. O custo de animação
também aguarda a cena controlada: o medidor direto está pronto, sem resultado
real de orçamento nesta entrega. O diagnóstico separado usa timer queries,
com glFinish desligado; seu caminho completo ainda precisa ser executado.
O CI comum não substitui o aceite da GPU. A fase 5 não foi iniciada.
Critérios, comandos e evidências atuais:
[revisão de aceite](docs/qa/animation-acceptance-2026-11-27.md).

### Checkpoint da fase 4 — 28/11/2026

O parecer seguinte liberou o início da fase 5 e transferiu uncapped/spikes
para essa comparação. O checkpoint de 30 s foi executado sem outro jogo,
PStats ou glFinish, na fonte da fase 4 com 20 comuns/6 famílias/chefe fase3,
500 partículas, cap60 e áudio. A primeira amostra falhou no p95 de animação
(4,2325ms) e foi preservada. Após reduzir vetores temporários e transforms
redundantes, o reteste passou: poses/views/mixer1,1347/1,4886ms; incluindo
arma/apresentação2,3124/3,0442ms (mediana/p95), aceito com nota conforme a régua
de2–4ms. Mediana de frame16,6673ms, p9516,7813ms, zero minimizações.
Essa referência não inclui os recursos de partículas da fase5.
Tabelas/dano/timings preservados; sem certificação de release.
[Relatório](docs/qa/animation-cpu-checkpoint-2026-11-28.md).

### Fase 5 — implementação e medições, 28/11/2026

Pool único com teto de 2.000 e 19 presets, LOD/reserva de combate, ambientação
das cinco áreas, feedback de combate/mobilidade/Slam/almas/level up e preparo
dos efeitos das fases tardias. Regras, dados de chefes e passo fixo preservados.
827 testes locais passaram; galeria nativa com 14 verificações e 35 pares de
sincronia aprovados. Banco do usuário preservado por hash.

Controles finais sem foco perdido ou minimização: referência livre
6,7988/11,9597 ms, candidata livre 8,0848/12,6205 ms (mediana/p95). Delta de
mediana +1,2860 ms **reprova** ±1 ms. O alvo histórico 3,665/7,0191 ms também
não foi atingido. O controle limitado separado teve mediana 16,6671 ms,
passando em 16,7 ms, mas 59,49 FPS reprovaram o piso adicional de 59,5 do gate.

Estresse final120,006 s, 2.000 partículas em todos os10.464 frames: máximo
29,414 ms, zero>50 ms. Animação inclusiva2,1875/2,9498 ms, aceita com nota;
partículas2,36425/3,2036 ms; passo fixo2,11145/2,9159 ms por passo.
São tempos de parede na thread do jogo, sem medição exclusiva de CPU/GPU.

Os gates foram executados e permaneceram reprovados. Não houve dispensa do
critério, seleção da melhor amostra, certificação de release ou início da
fase6. O pico histórico334,6945 ms continua sem causa estabelecida.
[Relatório e índice de hashes](docs/qa/particles-2026-11-28.md).
