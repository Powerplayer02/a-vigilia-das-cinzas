# Fase 4 — revisão de sincronia e preparação

Sincronia e preparo concluídos. **Desempenho continua sem aceite.** A escolha
mais recente do usuário foi “Faça a sincronia e o preparo; GPU depois”. Não
foram executados novos benchmarks de FPS nem diagnóstico GPU após essa escolha.
O custo real de animação na cena controlada também permanece sem medição.
A fase 5 não foi iniciada; o balanceamento beta permanece igual.

## Sincronia: falha reproduzida e correção

`tools/verify_attack_sync.py` verifica todas as definições dos três chefes nas
fases existentes: Vigia e Abadessa têm duas, Custódio tem três. São 35 pares,
dos quais 29 estão declarados nos movesets dessas fases; seis são definições
adicionais verificadas na fase 1. Não foram criados ataques ou fases novas.

O helper usa Fighter, AttackDefinition, volumes de `evaluate_pose`, a view de
produção e os métodos nativos de animação/arma. Primeiro observa volumes e
ativação, depois avança Fighter, constrói a view e aplica a pose, seguindo a
ordem real do jogo. O pico visual é a máxima projeção dos transforms lidos
dos NodePaths na direção geométrica da pose de impacto. Não se compara um
timestamp de animação inventado com uma cópia do mesmo timestamp lógico.

| Verificação | Antes (d16f1fdb) | Após correção |
| --- | ---: | ---: |
| Pares dentro de ±2 passos | 0/35 | 35/35 |
| Maior distância entre pico corporal e ativação | 28 passos | 1 passo |
| Sentido do desvio após correção | — | Pico um passo antes da ativação |
| Maior erro dos três pontos da arma durante contato | — | 0,00001932 unidade de mundo |

O corpo completava o acento depois do início do contato. Agora a parte final
da antecipação chega à pose de impacto no início da etapa ativa. O mixer
não aplica outro crossfade entre windup/active/recovery do mesmo golpe,
pois as curvas já são contínuas. Transições entre outros estados mantêm 85 ms.
A arma já seguia os pontos autoritativos; esse alinhamento continua verificado.
Projéteis usam `Attack.active` como janela de emissão, não uma hitbox de lâmina.

Todos os casos passaram com −1 passo (−16,67 ms), dentro de ±2 (33,33 ms).
O teste mede a pose enviada ao grafo a 60 Hz, sem janela: **não mede latência
do display/compositor nem legibilidade humana**. Os 35 casos integram o pytest.
AttackDefinitions, dano, tabelas de chefes e AST do passo fixo estão inalterados.

```powershell
python tools/verify_attack_sync.py --output artifacts/animation-acceptance/sync.json
```

## Preparação nativa sem mudar regras

Runtime instalado: **Panda3D 1.10.16**. Loading e transições agora combinam
`premunge_scene(gsg)` e `prepare_scene(gsg)` com o GSG da janela. O primeiro
otimiza formatos/geometria; o segundo submete recursos. Os renders sob
cobertura continuam percorrendo as poses representativas, sem tick do jogo.

Há um cuidado importante: premunge substitui Geoms. Executá-lo indiscriminadamente
sobre o pool dinâmico deixa o emissor com referências antigas para invalidar
os bounds. Por isso, premunge percorre o cenário de geometrias imutáveis e UI;
o preparo normal e os renders cobrem também os buffers mutáveis das partículas.
Não há atualização extra por frame para contornar esse problema.

O teste nativo offscreen verificou loading, troca para o Forno, 20 comuns com
as seis famílias reais e Custódio nas fases 2/3. Preservou snapshots, transforms,
RNG e os 90 passos de transição; a fila de recursos preparados do Panda estava
vazia após render. Também conferiu identidade de Geom/vertices/índices do pool
e leu no grafo os dados alterados pelo emissor após preparo/transições.
Esse ensaio funcional curto não é um benchmark ou aceite de GPU.

```powershell
python tools/verify_animations.py --area forno_da_vigilia --all-enemy-profiles --setup-only --output artifacts/animation-acceptance/native-setup
```

Os modelos são nós rígidos articulados, sem Actor/skinning por vértice.
Os shaders são GLSL explícito, sem `set_shader_auto`. Não se declara que
premunge compila universalmente shaders nem que o pico histórico foi eliminado.
Documentação: [NodePath](https://docs.panda3d.org/1.10/python/reference/panda3d.core.NodePath).
O comportamento destrutivo de premunge está na implementação
[GeomTransformer 1.10.16](https://github.com/panda3d/panda3d/blob/v1.10.16/panda/src/pgraph/geomTransformer.cxx).

## Medições preparadas, ainda pendentes

O workflow `render-performance.yml` mantém controles de 60 s após 5 s de
warmup, mesma máquina/resolução/semente e amostras não minimizadas. Gate:

1. Mediana com cap 60 ≤16,7 ms; média ≥59,5 FPS, conforme o protocolo anterior.
2. Mediana/p95 livres em ±1 ms do controle anterior e da referência aceita
   3,665/7,0191 ms.
3. Mais 120 s de poses do catálogo sobre combate de produção, 20 comuns com
   as seis famílias simultâneas, jogador, Custódio/fases 1/2/3 e 500 partículas;
   nenhum frame >50 ms. O helper registra cobertura efetivamente aplicada.
4. Medidor direto sem PStats/cProfile: pose lógica + view + mixer/transforms
   por render, média ≤2 ms; p95/máximo e amostras brutas também são registrados.
   Sincronização da arma e apresentação externa são relatadas separadamente,
   sem contar escopos aninhados duas vezes ou confundir médias por passo/render.

O estresse aplica poses sobre uma fixture com HP elevado e regras de produção.
Não afirma que todas as ações foram jogadas por comandos, nem mede dificuldade.
Os quatro controles estáticos mantêm a composição antiga para comparação;
a cobertura adicional de 120 s exige as seis famílias reais.
Não existe um único AnimationSystem ECS com todo esse custo na implementação
atual: as etapas reais acima são instrumentadas explicitamente.

O diagnóstico separado `tools/diagnose_gpu_timers.py` usa
`pstats-gpu-timing true`, **glFinish OFF**, e marca os frames de medição para
separar startup. Exige suporte ativo e dados de timer queries; não recorre
a glFinish se indisponível. Dados GPU sem correspondência exata de frame ID
ficam fora das estatísticas da janela medida e permanecem na captura bruta.
O caminho completo ainda não foi executado; o teste automatizado verifica
o relatório com dados sintéticos, incluindo a exclusão de um pico de startup.
Timer queries evitam sincronização forçada, mas o transporte/profiler ainda
tem custo. **Esse diagnóstico nunca é elegível como baseline de FPS.**
[Documentação PStats](https://docs.panda3d.org/1.10/python/optimization/using-pstats).

Os controles de FPS desligam explicitamente PStats, GPU queries e glFinish.
O runner dedicado ainda não foi provisionado; CI comum nas três plataformas
verifica contratos/regras, sem certificar a GTX1660Ti. Critérios permanecem
em aberto até o ensaio controlado autorizado para depois.

## Evidências e limites

[Índice verificável](animation-acceptance-2026-11-27.json): resumos, hashes de
fontes e dos relatórios locais antes/depois. Os relatórios brutos ficam em
`artifacts/animation-acceptance/` e não incluem save do usuário. Nenhum teste
de contato com a tela, escuta ou playtest humano foi fabricado.
Suíte local final: **799 testes passaram em 21,14 s**, preservando os 759
anteriores. O resultado remoto das três plataformas deve ser conferido no CI
do commit publicado; testes unitários não certificam desempenho gráfico.

A causa dos 334,6945 ms históricos continua desconhecida. O tempo de 65,8 ms
de PStats foi observado em uma chamada, não em todos os frames. A abertura
preta não reproduzida permanece apenas registrada. Não houve novo buff,
mudança de HP, dano, cadência, janela de parry ou regra de fogueira nesta revisão.
