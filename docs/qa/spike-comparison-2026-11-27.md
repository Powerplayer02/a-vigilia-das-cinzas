# Duas capturas distintas, conferidas pelos arquivos originais

| Captura UTC | Tempo de quadro | Situação | Maior chamada na pilha do quadro |
| --- | ---: | --- | --- |
| 24/11/2026 21:30:50.721330 | 333,680600 ms | Encerramento: `userExit → request_quit → _flush_save → save` | `sqlite3.Connection.__exit__`: 299,8825 ms |
| 27/11/2026 14:10:25.856476 | 334,694500 ms | Combate no Forno, Custódio fase 2, sem minimização | `GraphicsEngine.renderFrame`: 313,426 ms |

O registro `SessionStopped` da segunda sessão é posterior ao pico e tem pilha
distinta. A estimativa anterior de 14:12:15.419157 UTC / 109,56 segundos somava
`started_utc` a `wall_s`, mas esses relógios começam em lados diferentes da
inicialização da engine. Ela não oferece essa precisão e foi retirada.
O pico de 27/11 não é o save de encerramento de 24/11 com outro rótulo.
Tempos próximos, em dias e pilhas diferentes, não demonstram operação recorrente
de duração fixa nem causa compartilhada.

Na captura antiga o contexto diz `playing` porque é obtido no início do quadro;
a pilha contém a chamada de saída que aconteceu depois, dentro desse quadro.
A atribuição antiga ao commit de encerramento é sustentada pela pilha.
O teste posterior `artifacts/5.5/shutdown.json` registra **zero commits na saída**,
preservando o checkpoint anterior. Isso não explica o novo pico de renderização.

No quadro novo há 15,625 ms de CPU, nenhum GC registrado e nenhum commit SQLite
na pilha. Cerca de 18 ms de A* estão dentro dos 20,75 ms de `Game.frame`;
não explicam os aproximadamente 313 ms na chamada nativa de render.
A causa dessa espera permanece desconhecida. Não atribuir a shader/driver ou
eliminar I/O/SQLite/GC globalmente com base nessa amostra. Quarentena preservada.

Arquivos originais, sem alteração:

- `artifacts/5.4/spikes/spike_20261124T213050_721330Z.frame.pstats`
  SHA-256 `93af5c6ec23847d0714f7b2b953e173e7291fcdaf0cc84fb4f7bdc9cd84c3fca`.
- `artifacts/balance/custodian_tempo_final/spikes/spike_20261127T141025_856476Z.frame.pstats`
  SHA-256 `3fd6aa27f404d7f578bd093226b7ab028927f255798b9020862f91e2d448b940`.

# Esclarecimentos de balanceamento e áudio

**Custódio caiu na tentativa completa #1 do agente, em 3min20s.** O agente já
tinha experiência de parry nesse chefe. Um piloto minimizado e uma sessão
interrompida foram preservados e excluídos, não contados como derrotas humanas.
Os 121 HP de uma sessão anterior interrompida não são o resultado da vitória
final: ela terminou com **175,293/230 HP**. Não inferir dificuldade humana,
primeiro contato ou pressão percebida dessa tentativa. Balance OFF segue em aberto.
Mantidos HP 4.700 e os timings já publicados, sem novo aumento automático de fase 3.

O mixer SDL/pygame **real já foi verificado antes da fase 3**, com oito vozes
SFX simultâneas e duas vozes adicionais de música, em arena de chefe. Relatório:
`sfx-native-2026-11-27.json`. A soma PCM exportada não é captura da saída física.
O agente **não ouviu** o áudio. Clareza dos windups, mascaramento e coerência
musical precisam de escuta humana; nenhum teste de canal substitui essa escuta.

Dos 234 testes adicionados na fase 2: 106 exercitam evento, canal, prioridade e
preempção por SFX; 106 sintetizam PCM e verificam duração, formato e pico; os
22 restantes cobrem integração, configuração, variantes, cache e arquitetura.
Não são verificações de existência de arquivos. A fase 3 adiciona uma regressão
com cinco vozes ambientes: elas não podem tomar combate nem os canais de UI.
