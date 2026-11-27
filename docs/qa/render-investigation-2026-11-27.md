# Pico de renderização: evidência e investigação

Captura de **27/11/2026, 14:10:25.856476 UTC**, no Custódio **fase 2**,
durante comandos normais, relógio real e renderização **offscreen**. Não é
encerramento nem captura na fase 3. É um bloqueio real do processo de QA,
com potencial de afetar combate; sua ausência em benchmarks curtos não o resolve.

Arquivo acessível localmente:
`artifacts/balance/custodian_tempo_final/spikes/spike_20261127T141025_856476Z.frame.pstats`.
SHA-256 `3fd6aa27f404d7f578bd093226b7ab028927f255798b9020862f91e2d448b940`.

As cinco primeiras entradas, ordenadas por tempo cumulativo:

| Função | Chamadas | Tempo próprio ms | Tempo cumulativo ms |
| --- | ---: | ---: | ---: |
| `ShowBase.__igLoop` | 1 | 0,037 | 313,474 |
| `GraphicsEngine.renderFrame` | 1 | 313,426 | 313,426 |
| `play_balance.update` | 1 | 0,009 | 20,854 |
| `diagnostics.measured` | 5 | 0,021 | 20,758 |
| `Game.frame` | 1 | 0,037 | 20,744 |

Tempos cumulativos contêm chamadas aninhadas; não somar essas linhas.
O quadro completo levou **334,6945 ms**, com **15,625 ms** de CPU da thread.
Os 30 quadros anteriores do mesmo registro variam de **1,797 a 2,948 ms**.

Não há `Shader.load`, `Texture.set_ram_image`, upload Python de textura,
`sqlite3` ou `gc.collect` na pilha desse quadro. O monitor não registrou GC
Python. Há coleta interna de estados do Panda (`__garbageCollectStates`),
de **0,168 ms**, insuficiente para explicar o pico. `OnscreenText.getText`
levou 0,011 ms; `NodePath.set_shader_input`, 0,025 ms.

**O cProfile não detalha o interior da chamada C++ `renderFrame`.** Ausência
de `Shader.load` no Python não elimina compilação GLSL adiada no driver;
ausência de `set_ram_image` não elimina upload interno. Portanto não é possível
escolher shader, textura ou GC apenas pelas cinco primeiras linhas.
Nenhum `gc.freeze()` ou pré-aquecimento foi aplicado como correção presumida.

O gravador agora registra o tempo do estágio nativo e, antes/depois dele,
contadores de shaders, texturas, geometrias e buffers preparados/enfileirados,
além do tipo de janela. O teste `test_native_render_stage_retains_resource_counts_on_both_sides`
verifica a retenção desses dados. Essa instrumentação fica restrita ao modo
de diagnóstico e não é ativada nos controles de FPS.

Uma execução de diagnóstico separada usa `--split-flip`, log GLSL e amostragem
de GPU. Ela diferencia submissão/render de espera em flip e pode relacionar
novos recursos à captura. Não altera a política de apresentação do jogo normal.
Os resultados devem ser lidos com o custo da instrumentação identificado.

Execução separada da fase 3: 60,008s medidos após 5s de warmup, 20 comuns,
500 partículas, áudio ativo, cProfile e separação de flip, sem minimização.
Maior intervalo: **31,277ms**. Render/submissão: média 2,0976ms e máximo 9,4162ms;
flip: média 0,0075ms e máximo 0,1827ms. Não houve nova captura acima de 200ms.
O log contém duas entradas de compilação GLSL da preparação inicial.
Isso não reproduziu o evento antigo nem permite eliminar hipóteses para ele.
Dados e hashes em `sprites-render-probe-2026-11-27.json`; perfil e log bruto
ficam em `artifacts/sprites/render-probe/`. Esse controle força fase 3;
não cobre todo o histórico da luta original, cuja captura era da fase 2.

Estado: **causa nativa não identificada; bloqueador de lançamento e da fase 4**.
A quarentena antiga permanece. Publicar a arte após seus controles de desempenho
não é certificar o lançamento nem marcar esse problema como corrigido.
O evento antigo de SQLite, de 24/11, está separado em
`spike-comparison-2026-11-27.md`.
