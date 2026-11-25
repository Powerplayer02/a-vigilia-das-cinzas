# Fechamento da 1.0 — Etapa 5.5

Estado em 25/11/2026: 5.4 aceita funcionalmente; release ainda não certificada.

| Verificação | Estado |
| --- | --- |
| Testes locais de regras e contratos | 354 passaram no Windows, Python 3.13; os 306 anteriores preservados |
| Fechar a janela sem salvar | Corrigido e verificado por Alt+F4 real: zero commits no fechamento |
| Checkpoint coberto por preto antes do commit | Verificado por leitura do frame apresentado |
| SQLite | WAL, synchronous=NORMAL (1), estado anterior preservado após fechar |
| Repositório | Privado: Powerplayer02/a-vigilia-das-cinzas |
| CI remoto Linux/macOS/Windows | Aprovado: 306 testes em cada plataforma, [execução #1](https://github.com/Powerplayer02/a-vigilia-das-cinzas/actions/runs/45512808835) |
| Três desfechos a partir de saves anteriores ao chefe final | Aprovado: três fixtures versionadas, combate/epílogo/pós-créditos; repetido com Bullet/UI nativos |
| Campanha manual com números de produção | Pendente e bloqueia release |
| Comparação controlada de desempenho entre fases do chefe final | Pendente; não bloqueia release |
| Pico histórico de combate de aproximadamente 0,5 s | Não reproduzido na última campanha de QA; monitorado |

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

## Movimento Ágil — primeira etapa

Solicitado depois do recorte de fechamento: Dash + Slide, OFF por padrão,
save por personagem e testes com physics fake e Bullet sem janela. O loop
fixo permaneceu idêntico. HP, dano, resistências e IA de chefes não mudaram.
Wall jump/slam e o restante aguardam confirmação entre etapas.

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
