# Camada audiovisual — fase 1: música

As fases 1 e 2 cobrem música e efeitos sonoros. Sprites, animações,
partículas e acessibilidade aguardam as fases seguintes.

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
