# Camada audiovisual — fase 1: música

As fases 1/2 cobrem música/SFX e a fase 3 cobre atlas/UI. A fase 4 tem
sincronia corrigida e checkpoint de CPU medido. A fase 5 acrescenta partículas
e foi medida: estresse aprovado, comparação livre reprovada. Revisão atual:
[partículas, medições e limites](qa/particles-2026-11-28.md).
As seções abaixo preservam o histórico de cada entrega.

## Partitura original

`tools/music_gen.py --track patio_ambient --seed 17` exporta um WAV estéreo
44,1kHz, PCM 16-bit. `--all` prepara o catálogo com seeds derivadas de SHA-256
do ID, sem usar o `hash()` aleatório do Python. O algoritmo, a seed e o hash
de cada arquivo são registrados ao lado da faixa. Não há downloads de assets.

| Ambiente | Duração | Instrumentação |
| --- | ---: | --- |
| Pátio | 96s | Vento filtrado, coro distante, corda Karplus–Strong |
| Catedral | 96s | Órgão aditivo, coro, notas espaçadas |
| Pântano | 96s | Cordas dissonantes, ruído respirado |
| Ruínas | 96s | Percussão grave, baixo, eco de cordas |
| Forno/Forja | 96s | Ruído de fogo, metais e percussão |

Vigia, Abadessa e Custódio têm motivos originais de seis notas, preservados
nas variações de fase. Cada variação dura 96s; o Custódio inclui fase 3.
Menu: 30s em loop. Manter, Apagar e Transformar: 60s cada, sem loop.
Pós-créditos: 30s, depois retorna ao ambiente da área atual.

As notas e as caudas de reverberação atravessam circularmente o limite dos
loops. Os ambientes não terminam em fade para silêncio. Faixas de final têm
entrada e saída próprias e tocam uma vez. Saturação suave acontece apenas na
geração para controlar picos; não há processamento de síntese por quadro.

## Volume e formato

Alvo de −18 LUFS integrados no arquivo, antes dos controles de volume do jogo.
Medidor NumPy com ponderação K, blocos de 400ms, sobreposição de 75%, gate
absoluto de −70 e relativo de −10 LU, segundo
[ITU-R BS.1770-5](https://www.itu.int/rec/R-REC-BS.1770-5-202311-I).
O filtro por FFT trata o loop como periódico; não é certificação de true peak.
Metadados distinguem LUFS de pico por amostra. O teste inclui um sinal de 1kHz
com nível conhecido e um hash PCM fixo executado no CI das três plataformas.

O cache inicial usa **WAV**, também solicitado para o gerador, em vez de OGG:
mantém geração/reprodução sem encoder adicional e preserva o PCM determinístico.
Os arquivos são regeneráveis e ignorados pelo Git, em `assets/music/`.
Os antigos placeholders continuam em `assets/audio/music/` como fallback.
O catálogo inteiro cabe no orçamento de 500MB; tamanho medido no relatório QA.

## Integração e transições

`audio.procedural_music=true` em `data/config.toml` ativa a nova partitura.
`Config()` continua com a opção desligada para testes/benchmarks legados;
`tools/benchmark.py --procedural-music` mede a configuração nova explicitamente.

O boot verifica hashes e gera faixas ausentes/corrompidas **antes** de construir
o mixer. A primeira geração é mais lenta que as posteriores; nunca ocorre no
combate ou na entrada de uma área. Falha de escrita usa o áudio já disponível.
Sem dispositivo, o backend mantém o comportamento de continuar em silêncio.

Dois canais reservados, fora dos 32 canais de efeitos:

- Área → área: crossfade de 1,5s.
- Entrada na névoa: ambiente sai em 0,5s, tema entra em 1s.
- Fase 2/3: crossfade de 2s.
- Vitória do chefe: saída em 3s.
- Opções: música continua, reduzida em 6dB; saída restaura o ganho configurado.
- Créditos de um final: tema correspondente, uma vez. Voltar ao mundo inicia
  pós-créditos por 30s, seguido do ambiente. Créditos comuns mantêm o tema de menu.

O handler existente de eventos em `game.py` encaminha pedidos ao
`engine/music.py`. Não há novo subscriber de estado global nem chamadas ao mixer
em combate, mundo, IA ou jogador. `core/` e `model/` não importam NumPy/Pygame.
O passo fixo de gameplay permanece intacto.

## Validação

Testes sem janela: duas áreas com os dois canais ativos no meio da transição;
liberação do canal anterior; cancelamento de tema pendente ao sair da arena;
transição de fase; duck sem reiniciar a faixa; finais sem loop; retorno após
pós-créditos; normalização, seed, formato PCM e reparo de cache.

Balanceamento foi fechado em uma revisão separada antes da música. Resultados
e limitações da campanha: `docs/qa/balance-off-2026-11-26.md`. Medições de 60s
antes/depois e validação nativa de apresentação têm seus próprios relatórios;
não substituem avaliação humana de identidade musical ou comparação ON/OFF.

A conferência independente dos 17 WAVs com pyloudnorm 0.2.0 (filtro DeMan)
mediu erro máximo de 0,0003 LU para o alvo. Essa ferramenta e SciPy foram
instalados somente no ambiente local para auditoria, sem nova dependência do
jogo. O catálogo gerado ocupa 245.549.548 bytes (~234,2 MiB). Manifesto:
`docs/qa/music-assets-2026-11-26.json`.

No mixer real, o crossfade usa relógio monotônico para que o delta de um
carregamento anterior não adiante uma transição recém-iniciada. Em testes,
o relógio é injetável. O QA nativo carrega as duas geometrias reais e usa
uma Catedral sem inimigos como fixture de apresentação; não é outro teste
de dificuldade. A geração é proibida após o boot nesse ensaio. Registro:
`docs/qa/music-native-2026-11-26.json`.


## Fase 2 — efeitos sonoros

O gerador `tools/sfx_gen.py --all` cria 106 WAVs originais em `assets/sfx/`.
Há 93 presets incluindo aliases. Cada arquivo tem seed por ID, parâmetros de
ADSR, frequência, ruído, duração, pico e SHA-256. PCM estéreo 44,1kHz/16-bit,
regenerado antes do mixer se faltar ou estiver corrompido. O catálogo ocupa
7.309.392 bytes; nenhum arquivo externo é obrigatório.

Paletas para espada longa, machado, katana, cajado e maça: três leves por arma,
forte, corrida, dash e slide. Também impactos de carne/armadura/escudo,
parry/falha, críticos, stagger, mortes, movimento, quatro superfícies,
magia/impacto/dissipação, condições, menus, fogueiras, transições e chefes.
UI dura até 200ms, combate até 400ms; rugidos e cues de ambiente duram 1–3s.
Os sons partem de famílias compartilhadas com cores próprias por arma;
a coerência percebida e a ausência de mascaramento psicoacústico ainda
exigem oitiva humana. Não houve avaliação pelo ouvido pelo agente.

### Grupos e prioridade

`audio.procedural_sfx=true` ativa a fase. `[audio.buses]` define
`combat=1.0`, `ui=0.9`, `ambient=0.6`, `music=0.7`. Os sliders existentes
continuam controlando master, música e efeitos. Ganhos dos grupos são
multiplicadores internos, sem nova tela técnica no jogo.

O padrão continua com 32 vozes de efeitos mais dois canais de música.
Duas vozes de efeitos são exclusivas da UI. O teste reduz para oito vozes:
duas de UI e seis compartilhadas. Combate não ocupa as vozes reservadas;
ambiente perde para combate. Na mesma classe, a voz de menor prioridade e
mais antiga sai primeiro. Variantes alternam, sem tocar todas juntas.

Ordem de combate: rugido de fase 2 (95), transição (90), entrada (85),
morte de chefe (80), parry (70), críticos (65), impacto (40), passos (10).
Cues menos prioritários podem ser descartados quando todos os canais
apropriados estão ocupados. A UI também tem sua própria ordem e pode
substituir uma confirmação anterior, preservando o feedback recente.

A reserva garante reprodução sem roubo de canal; volume de grupo sozinho
não garante ausência de mascaramento. Ambiente é reduzido sob combate/UI,
e a UI recebe uma parcela própria da margem. Os sons de UI têm ataque curto
e banda distinta dos impactos graves.

### Proteção contra clipping

Picos dos arquivos: no máximo −4dBFS no catálogo atual (gate solicitado:
≤−1dBFS). O mixer lê os picos PCM uma vez no carregamento. Por quadro,
usa uma soma conservadora dos ganhos e picos para distribuir margem;
nenhuma síntese ou leitura de WAV acontece no combate. A soma é limitada
a 0,78 antes da quantização do mixer, incluindo música no volume máximo.
Esse limite deixa margem adicional para arredondamento de canais.

O teste soma os PCM de oito efeitos simultâneos e música, usando a política
de ganho de produção e todos os sliders em 100%, sem recortar amostras na
exportação. Pico medido: **−8,7261dBFS**. O arquivo é uma renderização de
verificação offline, não uma gravação da saída física nem aprovação auditiva.
Evidência: `docs/qa/sfx-mix-2026-11-26.json`.

### Disparos e limites

Widgets publicam feedback por callback da composição; `game.py` transforma
isso em eventos canônicos. Armas, impactos, parry, stagger, mortes e magia
usam os handlers existentes. Condições são observadas na apresentação, sem
avançar timers ou mudar HP. O teste verifica que o estado de domínio não muda.
Piso: pedra no Pátio/Forno, água na Catedral, lama no Pântano e madeira na
plataforma do Elevador; demais trechos das Ruínas usam pedra.

Morte de chefe dispara som no evento letal, sem esperar o fim da animação;
a música sai em três segundos. Recompensa posterior não repete o som.

Portas e baús que não possuem interação nesta versão têm cues gerados,
roteáveis e testados, mas não foram inventadas novas mecânicas para acioná-los.
Não confundir cobertura do catálogo com existência dessas interações.

A matriz de imports foi preservada. Uma verificação adicional proíbe chamadas
`play_sfx`/`play_music` em combate, jogador, mundo, IA e UI. O passo fixo é
idêntico ao da fase 1. Sprites/animações/partículas continuam em fases futuras.

### Picos históricos

Os benchmarks leves da fase 1 não estavam com flight recorder. Portanto,
seus bons percentis não eliminam carregamento, SQLite, GC ou compilação de
shader como causas históricas. Os perfis observados localizam parte do atraso
em renderização, sem identificar a causa nativa. Registros e quarentena
permanecem preservados; não foi aplicado `gc.freeze()` como suposta correção.


### Verificação final de 27/11

700 testes passaram em Linux, macOS e Windows na revisão dos efeitos
(`00658c5e`, CI 45909336947). Mixer real: oito vozes de SFX ocupadas, duas
reservadas para interface, mais dois canais de música; a interface continuou
com seu som. `docs/qa/sfx-native-2026-11-27.json` registra o resultado funcional
e a quarentena herdada do pico observado no combate.

Amostras sequenciais de 60s, após 5s de warmup, Custódio fase 3 + 20 comuns +
500 partículas, 1280×720 médio, GTX 1660 Ti, música ligada, sem cProfile:

| SFX | Limite | Mediana ms | p95 ms | FPS médio | 1% low |
| --- | --- | ---: | ---: | ---: | ---: |
| OFF | 60Hz | 16,6644 | 16,7348 | 60,01 | 59,37 |
| ON | 60Hz | 16,6653 | 16,7159 | 60,00 | 57,99 |
| OFF | Livre | 3,4393 | 6,4992 | 248,79 | 108,89 |
| ON | Livre | 3,5101 | 6,7743 | 241,36 | 102,14 |

Nenhuma amostra minimizada nas quatro execuções. Delta da mediana livre:
+0,0708ms, dentro de ±0,5ms; limitada: +0,0009ms. O par OFF/ON usa a mesma
tabela final do Custódio e isola a opção de efeitos. É uma medição local,
sem provar equivalência causal ou eliminação de engasgos raros.
Dados e hashes: `docs/qa/sfx-performance-2026-11-27.json`.

No reteste de balanceamento o gravador ativo registrou 334,6945ms: cerca de
313ms em renderFrame, sem GC no gatilho ou commit SQLite na pilha. Esse caso
foi triado, mas a causa nativa permanece não identificada e a quarentena foi
mantida. Os benchmarks leves não usam gravador. As duas modalidades não
podem ser combinadas para afirmar que o pico foi resolvido.

## Fase 3 — atlas e interface

Arte original desenhada por código: 36 células de ícones/molduras em um PNG
RGBA de 1024², com margem extrudada de 8px e 11 níveis de mipmap. A textura
é compartilhada pelo HUD, inventário, classes, mapa e menus. As molduras
preservam os cantos ao redimensionar; seu centro transparente não é desenhado.
Um arquivo TOML, `data/palette.toml`, controla os papéis de cor. A fonte existente
`assets/fonts/ui.ttf` é usada em todos os widgets; rasterização a 96 pixels/unidade
e filtro de mipmap mantêm a mesma família em títulos, corpo e botões.

O PNG e o manifesto são versionados; `python tools/sprite_gen.py` os regenera.
Ausência, corrupção ou paleta diferente acionam geração em memória, antes
do gameplay. Com `assets/` vazio, a interface usa a fonte da engine com
equivalentes legíveis para glifos ausentes e a arena usa seu shader embutido.
Dados de jogo continuam necessários em `data/`. Nenhuma dependência nova.

Os símbolos não substituem valores ou legendas: barras mantêm seus números,
status mantêm códigos e acúmulos, itens mantêm nomes e descrições. A escala
de HUD passa a admitir 80–150%; ela não aumenta a tipografia dos menus.
O QA de 1440p altera 150% pelo slider real das opções e verifica o texto
renderizado e os limites dos widgets, além do HUD ampliado com chefe e magia.
`tools/verify_ui.py` também exercita foco, pausa, equipar, level up e autosave;
o lock de slot é liberado antes da limpeza do save temporário no Windows.

O limite de prioridade de combate do áudio foi preservado. A regressão com
cinco vozes ambientes verifica que elas não tomam uma voz de combate nem
os canais exclusivos de UI. Isso não substitui escuta humana dos windups.

### Performance e CI de release

`tools/check_render_performance.py` bloqueia controles minimizados, curtos,
sem áudio ou com cenário incorreto. Exige 60s após 5s de warmup, 20 inimigos,
Custódio fase 3, 500 partículas, HUD completo, mobilidade OFF e a mesma semente
de escolha de golpes nas duas revisões. A cena não contém menu aberto.
Critérios: mediana limitada ≤16,7ms, média ≥59,5 FPS; deltas livres de mediana/p95
em ±1ms, com custo de mediana do HUD ≤0,5ms.

A primeira comparação falhou no p95: +1,0141ms, mesmo com mediana +0,1822ms.
Dados e fonte foram preservados em `artifacts/sprites/first-comparison/`.
Não foram considerados aprovação. Depois foi removido o quadrado central
transparente de cada moldura e a comparação passou a usar uma semente comum
no mesmo programa de medição. Os controles anteriores não são misturados
com os novos para escolher o melhor resultado.

Controle final local, mesma GTX1660Ti, 1280×720 médio, sem minimização:

| Revisão | Cap | Mediana ms | p95 ms |
| --- | --- | ---: | ---: |
| Fase 2 | 60Hz | 16,6656 | 16,7191 |
| Fase 3 | 60Hz | 16,6656 | 16,7060 |
| Fase 2 | Livre | 3,517650 | 6,7960 |
| Fase 3 | Livre | 3,665000 | 7,0191 |

Gate aprovado: delta livre +0,1473ms na mediana e +0,2231ms no p95.
As quatro execuções iniciaram 16 varreduras e 19 golpes verticais do chefe.
Dados, hashes, exclusões e primeira falha:
`docs/qa/sprites-performance-2026-11-27.json`.

O CI comum executa testes nas três plataformas; não possui baseline de GPU.
`.github/workflows/render-performance.yml` acrescenta o job manual/reutilizável
de pré-release: quatro controles sequenciais de 60s, validador e upload dos dados.
Requer runner dedicado com etiquetas `self-hosted`, `Windows`, `X64`,
`vigilia-gpu`, desktop interativo, driver e saída de áudio. Esse runner ainda
não foi provisionado nesta sessão; o job não é anunciado como executado.
Não substituir por renderizador de software em runner compartilhado para
certificar o orçamento da GTX1660Ti. O workflow pode ser chamado pela futura
pipeline de release antes da publicação do pacote.

### Pendências de lançamento

O Custódio mantém 4.700 HP e as tabelas já publicadas. Uma vitória do agente
experiente não determina tentativas humanas; balance OFF continua pendente
de playtest humano. A vitória terminou com 175,293/230 HP; os 121 HP citados
num parecer pertenciam a uma sessão interrompida. Escuta humana também pendente.

O pico nativo de334,6945ms continua como questão aberta de lançamento.
A fase4 foi posteriormente liberada pelo usuário, sem declarar causa ou cura.
A captura é de gameplay offscreen, fase 2, sem minimização; não é o commit
de saída de 24/11. Ver `docs/qa/render-investigation-2026-11-27.md` com as cinco
primeiras entradas, limites do cProfile e os novos contadores de recursos.
Publicar a arte após seu gate de desempenho não declara esse pico corrigido.

## Fase 4 — poses e mistura

`core/animation.py` define entradas de apresentação e canais de transformação.
`engine/animation.py` contém curvas procedurais e mixer por rig. A composição
produz `AnimationView` a partir de estados existentes; idade de ataque,
windup/active/recovery, parry, esquiva e transição continuam em60Hz autoritativos.
O mixer apresenta crossfade, respiração e locomoção contínua por velocidade.
Ele não recebe portas para física, dano, inventário ou persistência.

Há quatro sentidos de roll, backstep, ataques dos movesets existentes,
parry/guarda/impacto, críticos, beber com frasco, cast/uso de item, interação,
reações, stagger, knockdown, mortes frontal/traseira/fogo/queda, mobilidade
experimental e entrada/transição de chefe. As variantes de queda estão no
catálogo visual; não foi criada uma nova regra de morte por queda.
Ataques das fases2/3 recebem acentos de torso/cabeça. Não foram adicionados
ataques ou alteradas janelas para cumprir uma contagem artística.

O rig usa os modelos de blocos articulados existentes, agora com joelhos.
Durante ataques/guarda, armas e mãos seguem os pontos de combate existentes.
Respawn e invulnerabilidade mantêm seus timers; o fade de morte foi alongado
somente na apresentação para tornar a queda visível. Menus usam fade150ms;
cópias de saída têm seus PGItems desativados e são descartadas ao fim do fade.
Barras suavizam alterações sem modificar os números ou os recursos do jogador.

Cada área prepara99 entradas (incluindo etapas de ataques), mais o frasco e
os estados alpha/additive compartilhados do pool, sob cobertura preta. Tudo
é construído antes; não há malha, arquivo ou shader por nova pose. A transição
de chefe apenas agenda `prepare_scene` e usa o frame normal do rugido.
Isso amplia cobertura de preparação, sem provar eliminação de first-use ou
da causa histórica. [QA, protocolo e pendências](qa/animations-2026-11-27.md).

### Revisão de sincronia e preparo

O pico da pose corporal agora coincide com o início do contato em ±2 passos
nos 35 pares de ataque/fase existentes testados. A arma é conferida por três
pontos geométricos durante a janela ativa. O teste segue a ordem de produção:
resolver volumes, avançar Fighter, construir view e aplicar os transforms.
Elimina-se o crossfade adicional entre etapas contínuas do mesmo golpe;
as demais transições mantêm mistura. Dano e janelas lógicas não mudaram.

Além de `prepare_scene`, loading e transições usam `premunge_scene` no GSG
da janela. A passagem destrutiva de premunge fica no cenário estático e UI;
partículas mutáveis usam preparo/cache normal e renders representativos.
Não há Actor/skinning ou shader automático: são nós rígidos articulados e
GLSL explícito na versão 1.10.16. Não se afirma compilação antecipada universal.

O próximo ensaio cobre seis famílias reais simultâneas e registra os custos
de pose lógica, view, mixer/transforms, sincronização da arma e apresentação.
O total de animação soma somente escopos sem sobreposição, por render;
não soma duas vezes o custo da apresentação externa. O diagnóstico de GPU
usa `pstats-gpu-timing`, glFinish OFF, separado dos controles de FPS.
Esses números aguardam execução por decisão do usuário, assim como o aceite
de desempenho e a liberação da fase 5. [Protocolo atual](qa/animation-acceptance-2026-11-27.md).

## Fase 5 — partículas e ambientação, 28/11/2026

A liberação posterior permitiu implementar e medir a camada de partículas.
Há 19 presets num único pool de até 2.000, com dois lotes alpha/aditivo e
shader analítico compartilhado. O LOD reduz pedidos distantes e a ambientação
reserva espaço para combate. Cinco áreas, fogueiras, dano, mobilidade,
Slam, almas, level up e transições reutilizam esses recursos.

As formas e estados de blend são expostos no loading, incluindo os usados
pelas fases tardias. Transições só preparam recursos existentes. RNG visual,
snapshot, timers e partículas anteriores são restaurados. Pausa congela a
simulação e a luz; não se emitem segundos acumulados depois de um stall.

Buffers e scratch são reutilizados; índices só mudam com o blend. A névoa
usa a matriz de vista do motor e a luz usa o relógio GLSL com pausa/retomada,
sem reinstalar inputs na raiz por frame. Não há atlas ou variante por preset.
O shader fonte e o fallback seguem o mesmo contrato.

827 testes locais, 14 verificações nativas e os 35 casos de sincronia passaram.
O estresse de 120 s/2.000 partículas ficou abaixo de 50 ms em todos os frames.
A comparação livre final excedeu o orçamento de mediana em relação à fonte
anterior; o alvo histórico também não foi atingido. A camada está publicada
para revisão, sem aceite gráfico ou início da fase 6.
[Medições, falhas e evidências](qa/particles-2026-11-28.md).
