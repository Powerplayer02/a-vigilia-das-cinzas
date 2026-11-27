# Custódio — ritmo e pressão, 27/11/2026

A orientação mais recente do usuário prioriza um jogo emocionante e rápido.
O ajuste retira a vida extra do primeiro candidato e encurta o desgaste do
chefe, mantendo os aumentos de dano e cadência aprovados. Não altera as
fórmulas, os sinais de preparação, a poise ou as recompensas.

| Campo | Original | Final |
| --- | ---: | ---: |
| HP | 5.600 | 4.700 |
| Dano dos cinco golpes | 100% | 110% |
| Agressividade fase 1 / 2+ | 0,35 / 0,60 | 0,45 / 0,72 |
| Pausa de reposicionamento | 120 passos | 90 passos |
| Cooldown punição / agarrão / área | 180 / 240 / 300 | 150 / 210 / 240 |

A agressividade também regula aproximação. A frequência maior vem das
pausas e cooldowns, pois a chance de encadear ataques na segunda fase
continua definida pela FSM existente. Nenhuma janela de parry foi reduzida.

## Resultados observados

Original: uma vitória completa em 247,576399s, 180,266/230 HP restantes.
O primeiro candidato com 6.158 HP levou 273,469842s e terminou com
175,293/230 HP: aumentou a duração sem demonstrar pressão suficiente para
justificar a vida extra. Esse candidato foi descartado.

Configuração final: **200,167913s (3min20,168s)** entre entrada e golpe letal,
com 175,293/230 HP. Uma tentativa completa foi concluída nessa configuração.
Um piloto minimizado e outra sessão encerrada externamente não são usados
como duração de vitória; seus arquivos e anotações foram preservados.

A condução usa comandos normais, relógio real e renderização 3D sem janela,
como autorizado antes. Parte de um backup SQLite autêntico antes da névoa,
feito após compras normais: Cavaleiro nível 14, espada +2, 230 HP, 154 stamina,
Movimento Ágil OFF. Não injeta HP, posição, dano ou avanço de tempo.

O agente já tinha aprendido parry e usa sinais desenhados na cena; não é
avaliação humana de primeiro contato. Randomização e apresentação diferem
entre sessões. Portanto, esses números não isolam uma causa nem certificam
uma dificuldade definitiva. O reteste final ficou abaixo da referência de
210s; comparação ON/OFF da mobilidade permanece pendente.

Dados, hashes e identificação da fonte: `custodian-tempo-2026-11-27.json`.
O snapshot real anterior ao chefe tem SHA-256
`7635d6e308e19f2b9ccdf90c6a14e8a2a272d032df5affb05cc1d53e5541bb76`.
Bancos e eventos ficam em `artifacts/balance/`, sem substituir saves do usuário.

## Pico reproduzido

O gravador capturou 334,6945ms em combate, fase 2, sem minimização.
Cerca de 313ms estão em `renderFrame`; 20,75ms em `Game.frame`, com A*
representando cerca de 18ms dentro do passo fixo. CPU do quadro: 15,625ms.
Não há GC registrado ou commit SQLite na pilha do gatilho. Isso não elimina
essas hipóteses de todos os picos históricos e não identifica a causa nativa.
A quarentena foi preservada. Ver `sfx-spike-triage-2026-11-27.json`.
