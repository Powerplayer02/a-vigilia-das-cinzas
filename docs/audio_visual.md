# Camada audiovisual — fase 1: música

Somente música está no escopo desta entrega. SFX, sprites, animações,
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
