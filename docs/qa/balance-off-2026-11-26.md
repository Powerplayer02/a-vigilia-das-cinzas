# Campanha OFF e ajuste do Vigia — 26/11/2026

A campanha chegou aos créditos de **Transformar a chama**. O save real confirma
os três chefes derrotados, `ending=transform`, `credits_seen=true`, nível 14,
espada +2, 180,266/230 HP e 6.625 almas. SQLite `quick_check`: `ok`.

| Chefe | Tentativas | Vitória, tempo ativo | Personagem | Decisão |
| --- | ---: | ---: | --- | --- |
| Vigia | 9 | 8min23,359s | Cavaleiro nível 1, espada +0 | HP 3.200 → 2.720 (−15%) |
| Abadessa | 6 | 2min46,465s | Nível 9, espada +2 | Preservar valores |
| Custódio | 1 | 4min07,576s | Nível 14, espada +2 | Preservar valores; acima da referência de 3min30s |

O Vigia foi enfrentado no nível **1**, não 10–12. A condução evoluiu durante a
coleta; por isso, a duração longa não isola o efeito do HP. A redução de 15%
é uma iteração conservadora explicitamente pedida, não prova de calibração.
Só a linha `max_hp` de `data/bosses/warden.toml` muda o balanceamento.
Dano, resistências, poise, recompensas, timings, stamina e IA são preservados.
Os testes de limiar passam a usar metade de 2.720: 1.360, sem alterar a regra.

## Método e limites

Teste conduzido pelo agente com comandos normais, relógio real e Movimento
Ágil OFF por personagem; não é avaliação humana de dificuldade. Sem injetar
HP, dano, posição ou tempo. A política observa recursos próprios e sinais
desenhados (pose, cor, marcador de área e HUD), inclusive nós que podem estar
ocultos pela geometria. Isso limita conclusões sobre legibilidade para humanos.
O passo fixo de produção não foi alterado.

A campanha registrou cerca de 47 minutos ativos, com pausas de observação.
O Custódio inclui save/load normal durante a mesma tentativa para reabrir a
janela visível; a vida foi preservada e as pausas não contam na duração.
Uma morte causada por entrada física externa foi excluída e o efeito natural
no save foi mantido. Os intervalos brutos estão no arquivo de exclusões.

As cinco áreas foram percorridas pela rota principal. Catedral: dois guardas
eliminados, sem mortes. Pântano: um Carniçal, cinco mortes na Abadessa;
veneno chegou a 29% de acúmulo, sem ativação confirmada. Ruínas: acólito
eliminado por backstab, Elevador e atalho de ida/volta usados, sem mortes.
Forno: caminho ao Limiar e ao chefe, sem mortes; os dois comuns foram evitados.
Não representa eliminação de todos os inimigos nem exploração completa.
Somente um dos três finais foi jogado nesta sessão.

## Descanso confirmado

A decisão mais recente do usuário substitui a antiga: **preservar almas
carregadas e mancha; restaurar recursos e inimigos**. O código já corresponde
a essa regra. Notas antigas que chamavam a preservação de bug foram corrigidas
neste fechamento; não houve alteração da regra para zerar almas.

## Evidências e desempenho

Dados e hashes dos quatro saves reais:
`balance-off-playthrough-2026-11-26.json` neste diretório. Eventos, comandos,
imagens e bancos completos ficam localmente em `artifacts/balance/off_agent_01/`.
Não são os saves sintéticos de validação dos finais.

Os 18 perfis disponíveis foram triados antes da próxima medição. O pico mais
recente, em pausa, levou cerca de 332ms: 322ms dentro de `renderFrame`, com
31,25ms de CPU no quadro. Não há GC registrado no gatilho ou commit SQLite
na pilha. A causa nativa continua não identificada; não há evidência para
atribuir a shader, driver ou SQLite especificamente.

A coleta de comandos do agente varria mais de 500 arquivos a cada quadro.
Foi trocada por `scandir` e consulta ociosa a 10Hz, sem mudar os comandos
durante combate. Esse custo pertence à ferramenta de QA, não ao executável.
Perfis originais e quarentena histórica foram preservados. Uma medição leve
posterior não prova a eliminação desses picos. Detalhes e hashes:
`balance-off-spike-triage-2026-11-26.json`.

Comparação de chefes ON/OFF e validação humana permanecem pendentes. Os tempos
desta coleta não permitem declarar os três chefes definitivamente calibrados.

## Rechecagem do Vigia

Personagem novo, mesmos stats iniciais e espada +0: vitória em uma tentativa,
177.608s ativos, com 162,312/188HP. Confirma as duas fases e
parry/riposte com 2.720HP. A política já usa o aprendizado dos outros chefes;
não atribuir a diferença de duração apenas à redução de HP. Dados completos:
`warden-15pct-recheck-2026-11-26.json`.
