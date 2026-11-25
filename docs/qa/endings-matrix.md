# Matriz de desfechos — 25/11/2026

| Fixture | Ação depois da vitória | Epílogo | Save pós-créditos | Reload |
| --- | --- | --- | --- | --- |
| ending_a_preboss.db | maintain | Manter, distinto dos demais | ending=maintain, credits_seen=true | Gameplay com vitória preservada |
| ending_b_preboss.db | extinguish | Extinguir, distinto dos demais | ending=extinguish, credits_seen=true | Gameplay com vitória preservada |
| ending_c_preboss.db | transform | Transformar, distinto dos demais | ending=transform, credits_seen=true | Gameplay com vitória preservada |

As três fixtures são sintéticas, criadas pelo Game nativo com classe Mago e
dez pontos legais em Vigor. Chefe final a 5600 HP, inativo, jogador diante da
névoa; só Vigia e Abadessa estão derrotados, cinco áreas/fogueiras descobertas.
A intenção futura está no manifesto `tests/fixtures/saves/endings.json`,
sem alterar a regra do jogo: a decisão só ocorre no altar após a vitória.

Os casos de CI usam física e desenho falsos com combate, dano, timer de morte,
escolha e persistência reais. Os mesmos três fluxos foram repetidos em
processos nativos separados com Bullet, névoa e UI. O helper nativo reduz o
HP para o golpe final; não emite vitória artificial. Recompensa única,
evento `EndingChosenEvent`, texto exibido, crédito interrompido/reaberto,
retorno ao gameplay e leitura em processo limpo foram verificados.

Sem decisão: estado normal antes do altar, sem créditos concluídos.
None, valor desconhecido e duas decisões em lista/string: erro controlado,
save anterior intacto. Não há flags de sobrevivência de NPC a inverter.
O bloqueio por chefe ainda vivo e a imutabilidade após confirmar são testados.

Execução local: `python tools/verify_endings.py`. Geração intencional:
`python tools/verify_endings.py --generate-fixtures` (recusa sobrescrever).
Os PNGs e JSONs locais ficam em `artifacts/5.5/endings/`; não são prova de
campanha manual integral ou balanceamento.
