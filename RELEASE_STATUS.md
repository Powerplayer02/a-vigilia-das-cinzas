# Fechamento da 1.0 — Etapa 5.5

Estado em 26/11/2026: campanha OFF conduzida pelo agente concluída; fase 1
de música implementada. Release ainda não certificada; avaliação humana e
comparação ON/OFF dos chefes permanecem pendentes. As seções antigas abaixo
preservam a cronologia, e a atualização atual está no fim deste documento.

| Verificação | Estado |
| --- | --- |
| Testes locais de regras e contratos | 466 passaram no Windows, Python 3.13; os 438 anteriores preservados |
| Fechar a janela sem salvar | Corrigido e verificado por Alt+F4 real: zero commits no fechamento |
| Checkpoint coberto por preto antes do commit | Verificado por leitura do frame apresentado |
| SQLite | WAL, synchronous=NORMAL (1), estado anterior preservado após fechar |
| Repositório | Privado: Powerplayer02/a-vigilia-das-cinzas |
| CI remoto Linux/macOS/Windows | Aprovado: 466 testes em cada plataforma, [fase 1 de música](https://github.com/Powerplayer02/a-vigilia-das-cinzas/actions/runs/45903934895) |
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
