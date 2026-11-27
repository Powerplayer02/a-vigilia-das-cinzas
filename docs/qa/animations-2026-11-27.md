# Animações — implementação e limites de aceite

Nota histórica da entrega original. A correção de sincronia e o protocolo
atual, que substitui a cobertura de três famílias e as referências glFinish
descritas abaixo, estão em [revisão de aceite](animation-acceptance-2026-11-27.md).

Fase 4 liberada pelo usuário após o diagnóstico nativo, com causa histórica
aberta. A implementação está pronta para revisão funcional. **A medição final
de GPU foi explicitamente adiada pelo usuário**, portanto esta nota não dá
aceite de desempenho ou de lançamento.

## Escopo

Curvas procedurais sobre os modelos articulados atuais, sem novas bibliotecas.
99 entradas de pose:30 estados/gestos e69 etapas de23 ataques existentes.
São compartilhadas por jogador, seis perfis comuns e três chefes. O catálogo
inclui mobilidade experimental mesmo quando a opção do personagem está OFF.
Isso não ativa a mecânica nem cria dano fora das regras existentes.

Locomoção varia continuamente com velocidade; mudanças de estado misturam
poses por 85 ms. Esquivas preservam direção inicial. Ataques usam idade/timings
de produção. Chefes têm entrada, transição/roar e acentos das fases 2/3 sobre
seus movesets. Não se adicionaram quatro ataques de gameplay a fases que
possuíam menos. Os modelos continuam sendo blocos articulados procedurais.

Clipes de mortes por trás/fogo usam o evento de dano. O catálogo também cobre
queda, sem nova regra letal. Reações leves e stagger/knockdown, itens, interação,
magia e movimentos ágeis reutilizam estados/eventos já existentes.
Durante contato ativo, a arma desenhada mantém os pontos calculados pelo
combate. As animações não dirigem Bullet. A AST de `Game._fixed_step` e os
arquivos de balanceamento de chefes são idênticos à revisão6d079709.

## Preparação e transição de fase

No boot e na troca de área, a composição constrói os equipamentos visuais,
expõe temporariamente os dois draw states do pool de partículas e apresenta
uma pose de cada entrada sob a cobertura preta. Rigs fora da câmera são
temporariamente posicionados na vista de preparação; transforms, câmera,
partículas, ordem da lista livre e RNG visual são restaurados. Não se chama
`Game.frame`, física ou tick de regra durante essa sequência.

O evento real de fase enfileira recursos já criados. Antes do render normal,
`prepare_phase_resources` prepara os nós e o pool já visível pelo evento.
Não há `render_frame` recursivo, bloqueio explícito ou geração de assets no
handler. O frame do rugido consome a fila. Cada par chefe/fase é preparado
uma vez por cena. Isso evita introduzir carga síncrona extra no passo fixo.

Os testes nativos percorreram Vigia, Abadessa e Custódio, com os seis perfis
comuns distribuídos entre as galerias. Verificaram snapshots e transforms
idênticos após aquecimento. Nas transições 2/3 do Custódio e2 dos outros,
restaram os mesmos 90 passos de transição e zero recursos na fila de preparação
do Panda após o render de verificação. Isso não mede a fila do driver.
Não houve avanço de ataque/HP/RNG nessa preparação.
Esses ensaios são fixtures de apresentação, sem certificação de dificuldade.

## Interface

Fade150 ms para painéis e cópias de saída não interativas, brilho de foco,
efeito de pressão nativo e easing de barras. Os valores numéricos seguem
imediatos. O teste de troca de alvo da barra verifica que uma cura/dano novo
interrompe o easing anterior sem manter valor incorreto. A cópia que sai
desativa seus PGItems; o QA exige liberação após o fade.
Galerias de UI exercitam26 estados, escala150%, e fallback sem assets.

## Desempenho — pendente, com falhas preservadas

Base copiada da revisão6d079709, controles60 s após 5 s de warmup,1280×720 médio,
Custódio fase3 +20 comuns +500 partículas, música/SFX ON, mobilidade OFF:
mediana/p95 limitados16,6662/16,7268 ms; livres3,68865/7,4246 ms.

A primeira candidata limitada teve mediana16,6717 ms, p9519,520 ms e58,36 FPS;
não atingiu a média anterior de59,5 FPS. O ensaio livre seguinte foi minimizado
por333 frames (~41,56 s) e é inválido. Um smoke de2 s não serve como baseline.
As amostras e diagnósticos curtos permanecem em `artifacts/animations/`, sem
selecioná-los como aprovação. Houve atividade concorrente de outro jogo e
alterações posteriores no cache de poses/setters. A versão final ainda precisa
ser medida em condições controladas; nenhum desses números a certifica.

Protocolo preparado no workflowGPU, ainda não executado nesta revisão:

1. Quatro controles nativos sequenciais60 s/5 s, sem PStats/cProfile/PNG encoding.
2. Mediana limitada≤16,7 ms; média≥59,5 FPS; mediana/p95 livres em±1 ms do controle
   correspondente e da referência aceita3,665/7,0191 ms.
3. Mais120 s com catálogo inteiro, três famílias comuns e chefe em fases1/2/3;
   nenhum quadro acima 50 ms. O fixture aplica poses sobre o combate de produção,
   com HP de estresse, e não é um playthrough de todas as ações pelo teclado.
   `animation_workload` registra cobertura e tempo do mixer por render/ator.
4. Referências curtas com/sem `gl-finish`, usando contadores diretos e flip
   separado, excluídas do aceite de FPS.

`tools/check_animation_performance.py` rejeita amostra minimizada, incompleta,
instrumentada com PStats, curta, com pico>50 ms ou sem pares clipe/fase. O gate
HUD de0,5 ms permanece para comparações só de UI; o pacote de animações usa o
orçamento total de±1 ms autorizado. O runnerGPU dedicado continua necessário.

## Interpretação do diagnóstico e balanceamento

App alto não prova causa CPU/loader, e diferença entre duas execuções não
quantifica cache de driver. Mudar `gl-finish` altera sincronização; subtrair
dois máximos não mede trabalho enfileirado nem prova vazamento de estado.
A espera de65,8 ms do PStats foi observada numa chamada, não em todo frame.
O mecanismo dos334 ms históricos permanece desconhecido. O aquecimento não
é apresentado como eliminação da classe inteira de first-use.

A abertura preta já ocorreu com aquecimento ativo e não se repetiu em dois
controles subsequentes. Registro preservado, sem nova perseguição ou causa
presumida. A liberação da fase 4 não altera essas conclusões históricas.

Custódio continua com 4.700 HP, dano+10% e cadência vigente. Vitória completa#1
do agente experiente:200,167913 s,175,293/230 HP. Vigia mantém 2.720 HP (−15%).
Não foi medida dificuldade humana ou legibilidade subjetiva dos sinais.
O formulário de beta coleta equipamento, tentativas, pressão/telegraphs e
engasgos; patches de HP/dano/cadência serão guiados por esses relatos. Não foi
aplicado novo aumento de agressividade só para fabricar um pico de dificuldade.

Índice com hashes, relatórios nativos e resultados dos testes:
`animations-2026-11-27.json`. Nenhum save do usuário foi usado como fixture.
