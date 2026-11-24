# Fechamento da 1.0 — Etapa 5.5

Estado em 24/11/2026: 5.4 aceita funcionalmente; release ainda não certificada.

| Verificação | Estado |
| --- | --- |
| Testes locais de regras e contratos | 306 passaram no Windows, Python 3.13 |
| Fechar a janela sem salvar | Corrigido e verificado por Alt+F4 real: zero commits no fechamento |
| Checkpoint coberto por preto antes do commit | Verificado por leitura do frame apresentado |
| SQLite | WAL, synchronous=NORMAL (1), estado anterior preservado após fechar |
| Repositório | Privado: Powerplayer02/a-vigilia-das-cinzas |
| CI remoto Linux/macOS/Windows | Em publicação; resultado ainda não certificado |
| Três desfechos a partir de saves anteriores ao chefe final | Pendente: QA 5.4 ramificou um snapshot pós-vitória |
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
ocultos. Isso não substitui a matriz funcional pré-chefe ainda pendente.

O QA 5.4 utilizou HP, precondições e teleporte sintéticos declarados.
Ele valida o fluxo, mas não certifica tempo de combate, dificuldade ou
balanceamento. Não foram realizados três playthroughs manuais completos.

O plano antigo de mini-chefes e novas expansões foi substituído pelo
fechamento de release. Sentinela Oca e Viúva das Cinzas ficam fora da 1.0.
Nenhuma tag ou release 1.0 deve ser criada enquanto os bloqueios persistirem.
