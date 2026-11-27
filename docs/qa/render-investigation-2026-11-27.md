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
Nenhum `gc.freeze()` foi aplicado. O pré-aquecimento defensivo descrito abaixo
não é apresentado como correção da captura antiga.

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

Estado deste diagnóstico: **causa nativa não identificada; questão aberta de lançamento**.
A fase4 foi posteriormente liberada pelo usuário, mantendo a causa aberta.
A quarentena antiga permanece. Publicar a arte após seus controles de desempenho
não é certificar o lançamento nem marcar esse problema como corrigido.
O evento antigo de SQLite, de 24/11, está separado em
`spike-comparison-2026-11-27.md`.

## Novas reproduções com PStats nativo — 27/11

O arquivo antigo `.frame.pstats` é do **cProfile do CPython**. Não contém barras
nativas recuperáveis. Para obtê-las nas novas sessões, `tools/native_pstats.py`
usa o `text-stats` oficial do Panda3D **1.10.16**, eventos nativos `-r` e tempos
hierárquicos inclusivos. Não soma pais com filhos. A saída nativa comprimida,
os números de frame e lacunas de entrega são preservados; o servidor exibe o
frame mais recente e pode descartar intermediários. Não é benchmark de FPS.

`tools/diagnose_custodian.py` copia o save autêntico pré-chefe, usa os comandos
originais de Continuar e da rota, depois controla o combate com relógio real.
Não injeta HP, posição, fase ou dano. Cada execução tem diretório próprio e
cache **de modelos do Panda** isolado por configuração do processo. Nenhum
cache global ou do driver NVIDIA foi apagado. O shader atual informa
`get_cache_compiled_shader() == False`; não há evidência de que o cache do
driver esteja frio. Portanto “cache limpo” não equivale a uma compilação de
driver garantida, nem um novo engasgo provaria compilação de shader.

Três replays completos percorreram as fases 1/2/3:

| Execução | Configuração | Maior Main nativo ms | App ms | Cull ms | Draw ms | Wait ms | Maior Main com chefe ativo ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| cold | cache Panda novo, gl-finish OFF | 552,660 | 550,476 | 1,096 | 0,573 | 0,210 | 33,051 |
| warm | mesmo cache Panda, gl-finish OFF | 259,201 | 253,087 | 0,414 | 2,129 | 0,064 | 63,845 |
| finish | outro cache Panda novo, gl-finish ON | 392,100 | 2,276 | 0,668 | 384,341 | 0,152 | 122,711 |

Os maiores quadros da tabela ocorreram **antes de o chefe ficar ativo**, em
carregamento/pausa. Não reproduziram o evento histórico de combate na fase 2.
O quadro cold com QA clock 118 também levou 244,150 ms: App 242,641,
Cull 0,480, Draw 0,564 e Wait 0,099 ms. Seu parceiro cProfile mediu 244,149 ms;
o quadro cold QA 212 teve parceiro cProfile de 552,717 ms. Esses pares permitem
ler eventos diferentes sem confundir IDs nativos com o contador do relógio.

Não há barra Flip separada nessas capturas offscreen. `Wait` não foi renomeada
para Flip. Tempos de consultas GPU podem atravessar uma espera do CPU e não
provam atividade contínua da GPU durante todo o intervalo.

Nos dois quadros cold, a maior lacuna nos eventos nativos fica **depois do fim
de App:Cycle e antes do fim de Frame**: 239,479 e 539,511 ms. Nesse trecho,
`GraphicsEngine::render_frame` ainda executa o relógio e `PStatClient::main_tick`.
O segundo também reduz buffers preparados de VBO125/IBO132 para VBO39/IBO38;
texturas e shaders não aumentam. Isso restringe a investigação, mas não basta
para nomear shader, modelo ou driver como causa. Comunicação do profiler e
escalonamento da thread também precisam ser considerados.

Um controle com saída nativa **bufferizada**, um bloco de 60s e cache Panda
novo não teve captura cProfile acima de 200 ms. Maior Main recebido: 159,356 ms;
com chefe ativo: 67,401 ms. Seu relógio foi conferido como `M_normal`, sem cap.
O controle cobre fase 1; não substitui os três percursos completos.
`smoke` (parser anterior) e `buffered` (falha de inicialização) ficam preservados
e excluídos. A instrumentação e sua própria saída introduzem carga; estes
números não são comparações de desempenho entre revisões.

`gl-finish` mudou a distribuição dos picos novos, mas também mudou a execução.
Isso não torna o teste uma prova binária de CPU versus GPU, nem resolve o
evento antigo. A documentação alerta para o custo dessa opção.

### Controle das próprias funções nativas

Com Frida17.28.0, hooks de entrada/saída mediram `render_frame`,
`ClockObject::tick`, `PStatClient::main_tick`, `client_main_tick` e
`transmit_control_data` no filho do replay, sem alterar os binários Panda.
Uma nova luta completa, com fases1/2/3 e **sem conexão PStats**, registrou
87.224 chamadas: máximo de `render_frame`104,0041ms, relógio0,7748ms e
`main_tick`0,5376ms. `transmit_control_data` não foi chamado. O gravador
cProfile não disparou acima de200ms; o arquivo `worst_*` também preservado
é o pior quadro abaixo do limiar, não uma nova captura de spike.

Em outro controle de60s, agora com PStats conectado, 25.163 chamadas deram
máximo71,7249ms em `render_frame`. Dentro da mesma chamada lenta, houve
66,0103ms em `main_tick` e **65,7979ms em `transmit_control_data`**, com relógio
máximo0,0883ms. Isso localiza uma espera nova na comunicação do profiler,
e demonstra que App não identifica automaticamente um carregamento de modelo.
Os tempos aninhados não devem ser somados. O segundo controle cobre fase1.

Esses resultados mostram interferência mensurável da instrumentação, mas não
atribuem a ela os picos cold anteriores, que não tinham esses hooks, nem o
histórico334ms, que não tinha a conexão PStats. Não há nova reprodução desse
evento em combate, e os hooks também têm custo. Nenhum resultado foi usado
como aprovação de FPS ou alegação de cura.

## Mitigação defensiva e decisão editorial

`main.py` agora chama `prewarm_scene` sob uma cobertura preta, antes de iniciar
o gravador e o loop: apresenta a cobertura, enfileira os recursos da cena e UI
já construídas, renderiza duas vezes e sincroniza. Não roda tasks de gameplay.
Teste nativo offscreen: **65,8441 ms**, três renders, zero passos de simulação,
snapshot idêntico antes/depois. Testes cobrem ordem e remoção da cobertura
também se o render falhar. Não prepara assets de áreas/fases ainda não criadas
e não existe evidência de que tenha corrigido o pico histórico.
Os replays acima não chamam essa função; ela teve verificação nativa separada,
não uma comparação causal do pico com/sem aquecimento.

Na versão instalada, `GeomNode::prepare_scene` enfileira também shaders e
buffers de vértices/índices, além de texturas. Citações de outras versões que
negam isso não descrevem o código usado aqui. Renderizar e sincronizar após
enfileirar continua sendo a medida defensiva; futuros assets precisarão de
preparação no seu próprio carregamento.

Escolha de balanceamento: **(c), beta com feedback**. HP4.700, dano e cadência
do Custódio preservados. README, status e formulário de issues deixam explícito
que não há medição humana de dificuldade. A vitória do agente não permite
prever tentativas humanas nem declarar que o chefe está fácil ou balanceado.

Referências primárias:

- [PStats e medição de GPU no Panda3D1.10](https://docs.panda3d.org/1.10/python/optimization/using-pstats).
- [Preparação de recursos em GeomNode, versão1.10.16](https://github.com/panda3d/panda3d/blob/v1.10.16/panda/src/pgraph/geomNode.cxx).
- [Ordem de render_frame, versão1.10.16](https://github.com/panda3d/panda3d/blob/v1.10.16/panda/src/display/graphicsEngine.cxx).
- [Servidor text-stats, versão1.10.16](https://github.com/panda3d/panda3d/blob/v1.10.16/pandatool/src/text-stats/textMonitor.cxx).

Evidência bruta local: `artifacts/render-investigation/`; índice com hashes em
`render-native-2026-11-27.json`. A causa do evento histórico continua aberta;
a fase4 foi posteriormente iniciada com autorização explícita, sem release novo.
Implementação e pendências atuais: `animations-2026-11-27.md`.

Para repetir com um save pré-chefe próprio, em diretório novo:

```powershell
python tools/diagnose_custodian.py --save CAMINHO_DO_SAVE --directory artifacts/novo-replay --cache artifacts/novo-cache --buffered
```

A opção `--gl-finish` ativa o experimento de sincronização. `--trace-native`
usa Frida, instalado separadamente apenas no ambiente de diagnóstico, para
cronometrar exports nativos da engine no processo filho identificado pelo
próprio PID. `--no-pstats` permite o controle sem conexão ao profiler Panda.
Nenhuma dessas opções muda as dependências do jogo.
