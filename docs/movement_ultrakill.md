# Movimento Ágil — etapas 1 a 3 experimentais

Desligado por padrão em `[movement] ultrakill_style = false`. A opção fica
em Opções → Controles. O personagem guarda seu próprio modo e os timers;
carregar outro personagem restaura a opção dele. Saves anteriores ficam OFF.
Desligar sob um teto baixo exige primeiro sair do obstáculo.

## Implementado nesta etapa

| Ação | Passos a 60 Hz | Regra |
| --- | --- | --- |
| Dash | 12 (0,20 s) | 4,5 m livres, oito direções relativas à câmera |
| Invulnerabilidade do dash | 1–6 | Passos 7–12 vulneráveis |
| Recarga | 72 por carga | Duas cargas; recarga sequencial, sem custo de stamina |
| Kill creditado ao jogador | Imediato | +1 carga, sem duplicação; ao encher, zera o timer |
| Rastro | 15 (0,25 s visuais) | Pool de 16 silhuetas translúcidas preparado ao ativar |
| Slide | Até 36 (0,60 s) | Corrida + movimento, 14 stamina, velocidade inicial 5,8 × 1,4 m/s |
| Ataque de slide | 9 / 5 / 20 | Windup / ativo / recovery, 18 stamina, pacote do leve × 1,6 |
| Ataque de dash | 8 / 6 / 24 | 24 stamina, pacote do leve × 2,0 |
| Salto de slide | Impulso vertical de 7 m/s | 12 stamina, horizontal atual × 1,2 e decaimento de 24 passos |

O dash desacelera nos últimos três passos, com pesos 0,75 / 0,50 / 0,25.
A velocidade inicial é normalizada para que a soma dos 12 deslocamentos
seja 4,5 m. Colisões encurtam o trajeto; não há teleporte através de paredes.
Sem direcional, o dash segue a câmera. A diagonal não ganha velocidade.

Ataque leve, forte, conjuração e parry interrompem o dash. Outro dash gasta
outra carga e troca a direção. Ele não começa durante ataque, stagger ou
morte. Dano nos seis primeiros passos respeita i-frames; depois disso pode
interromper normalmente. O dash não limpa stagger nem revive o personagem.

Slide exige chão e corrida. Soltar, dar dash ou pular o encerra. Ataque leve
durante slide usa `SLIDING`, separado do running attack. Não há i-frames.
Seu deslocamento desacelera linearmente. O salto básico e suas tolerâncias
só existem no modo experimental.

## Colisão e arquitetura

O domínio é `player/advanced_movement.py`, com vetores puros, interfaces de
`core/protocols.py`, timers inteiros e eventos. Nenhuma chamada de áudio ou
Panda3D entra nesse módulo. Input mantém remapeamento de teclado e gamepad;
com OFF, dash, slide, jump e Slam são filtrados antes de entrar na fila.

A cápsula baixa tem exatamente metade da altura e preserva os pés. O
adaptador Bullet reutiliza dois controladores e verifica espaço antes de
voltar à cápsula normal. Essa escolha respeita a [API do Panda3D 1.10](https://docs.panda3d.org/1.10/python/reference/panda3d.bullet.BulletCharacterControllerNode),
que expõe a forma do controlador para leitura. As posições e volumes dos
ossos são rebaixados depois da leitura da física e antes dos contatos.

O corpo de `Game._fixed_step` foi preservado. A FSM de combate recebe a
referência opcional ao controlador ágil; as intenções continuam vindo antes
de `physics.step`, e a sincronização das hitboxes continua depois. Lock-on
permanece ativo. Nenhuma FSM de inimigo ou chefe foi alterada.

SFX próprios e rastro recebem eventos. O modo OFF não cria o controlador,
pool visual, rastro ou cápsula alternativa. O relógio de render controla
somente a apresentação; combate e recargas usam o passo fixo.

## Etapa 2 — wall jump e Slam

No ar, direcional contra uma parede inicia cling ao detectar uma superfície
frontal a até 0,5 m, com normal oposta ao movimento. Dura até **24 passos**,
sem velocidade vertical/horizontal. **B** lança para longe da parede, custa
12 stamina e usa impulso vertical `7 × sqrt(1,3)` m/s: altura teórica 30%
maior que o salto básico. Dash só pode sair paralelo ou para longe da parede.
Receber dano cancela cling. A mesma superfície não pode ser agarrada outra
vez antes do chão; a identidade estável do colisor evita burlar a regra por
variação de normal. Fakes sem identidade usam a chave de plano geométrico.

**G no ar** inicia Slam, por 18 stamina. O corpo desce a **18 m/s**, sem
i-frames. Consultas preveem o apoio dentro do próximo passo, incluindo
personagens e bordas sob a parte arredondada da cápsula. O corpo limita o
deslocamento físico e emite **um** `SlamImpactEvent`, inclusive ao cair sobre
um alvo cujo colisor não participa dos raycasts de câmera/cenário.
O impacto cobre raio horizontal de **2,5 m**, com filtro de altura e linha
de visão, 40% do pacote elemental/físico do ataque leve antes da mitigação
e **60 de poise damage**. Recuperação de **8 passos**, também vulnerável.
Ondas e som vêm do evento. No gamepad experimental, Slam usa direcional
esquerdo; nos menus, continua sendo navegação. Tudo aceita remapeamento.

`player/advanced_movement.py` não importa combate nem engine. Publica dados
puros. O `CombatSystem` assina o evento, enfileira e resolve depois da física.
O autor é opcional: fornece facção, scaling e crédito quando existe; o teste
sem atacante/sem hitboxes também resolve. A fila de áreas é compartilhada
com as zonas de fogo. Dano, resistências, poise, morte e eventos usam `_hit`
e `resolve_damage`, em vez de uma segunda fórmula de dano. Aliados e autor
são filtrados quando a facção é conhecida. Ataques sem autor podem ser neutros.

O estilhaço mágico atual é raycast; globos dos chefes usam `CENTER_SPHERE`.
Eles já usam o mesmo resolvedor de dano. Não foi criada uma magia AoE nova.
`test_architecture.py` proíbe import de combate e bibliotecas nativas no
controlador avançado; `test_slam.py` valida impacto mockado com múltiplos alvos.

O adaptador usa motor vertical sem gravidade durante cling/Slam e o voo do
wall jump. Restaura o controlador normal e a gravidade ao aterrissar, cancelar,
trocar de área ou respawnar. O mesmo corpo lógico permanece no ECS, com apenas
um controlador físico ativo. Timers, superfícies usadas, modo vertical e
interrupção pendente são persistidos; carregar a recuperação não repete dano.
O corpo de `Game._fixed_step` continua idêntico.

## Etapa 3 — momentum e tolerâncias do salto

Sair de dash/slide preserva a **última velocidade horizontal**, e cancelar
dash com ataque preserva a velocidade daquele passo. Durante os 24 passos
seguintes, sem input, ela decai linearmente até zero. Com direcional, a
mesma interpolação converge para a velocidade normal de andar/correr;
não soma velocidades nem renova a janela. Corrida mantém seu custo normal.
Após um dash completo, o trecho adicional sem input mede cerca de **1,339 m**.
O salto de slide recebe o impulso de 20% e também passa por essa curva.

O ataque leve escolhe uma definição própria no moveset: `dash_attack`
(`DASH_ATTACK`) ou `slide_attack` (`SLIDING`, nome preservado para saves).
Os pacotes de dano e poise já contêm os fatores **2,0** e **1,6** do leve,
respectivamente. `walking_attack` usa **1,1**, preservando a ordem dash >
slide > corrida > andar > parado nas cinco armas. Corrida usa a definição
que já existia. Caminhar com OFF continua usando o leve original.

A seleção ocorre no input: passos **1 e 24** após o dash recebem a variante;
nos passos **25 e 30**, ela expirou. O pacote selecionado permanece estável
durante windup/ativo/recovery. A janela não foi alongada sem uma avaliação
de uso; decidir se 24 passos são suficientes para o jogador pertence ao
balanceamento ON. Encostar em inimigo sem ataque ativo não causa dano:
a opção A usa os contatos normais de hitbox/hurtbox, sem dano passivo por toque.

Cling zera o momentum horizontal. O wall jump parte só de seus impulsos
próprios, sem adicionar a velocidade anterior do dash. Roll substitui o
impulso pelo perfil original da esquiva e não o restaura ao terminar.
Riposte/backstab conservam a pose estacionária anterior. Stagger, morte,
Slam e desativar o modo também limpam a herança.

**Coyote time:** permite pular nos seis passos após sair de uma plataforma.
**Jump buffer:** guarda a borda de B no passo do input e nos seis passos
seguintes, acionando ao aterrissar. As duas janelas são consumidas juntas
quando um salto acontece; manter B pressionado não produz novo salto.
Não criam salto aéreo ao nascer no ar, não dispensam stamina e não ignoram
espaço para levantar a cápsula. Roll limpa o input pendente.

O motor vertical controlado também atende o salto básico/coyote: a física
continua resolvendo colisões, e a velocidade vertical fica disponível ao
save. Momentum, origem, último impulso e idades das duas janelas são
persistidos sem reiniciar os timers. Os campos novos têm defaults neutros
para saves das etapas anteriores, incluindo ataques de slide em andamento.

`damage.py` e sua assinatura permanecem idênticos. A suíte protege seu hash,
os imports preexistentes de combate em `player/` e o hash de `_fixed_step`.
`test_momentum.py` cobre as variantes e suas interações; `test_coyote_buffer.py`
cobre os limites 6/7, as janelas simultâneas e colisão Bullet real.
`tools/verify_momentum.py` repete o fluxo no Game, com save/load e gravador.

## Protocolo de desempenho

A régua anterior de ±5% de FPS foi substituída: **60 s**, warmup de 5 s,
clock limitado a 60 Hz, frame time em ms, mediana e p95. A mediana OFF deve
ficar até **+1,0 ms** do checkpoint pré-Ultrakill. Foram medidos 16,6665 ms
no checkpoint, 16,6646 ms na etapa 1 OFF e 16,6651 ms na etapa 2 OFF; p95
respectivos de 16,7601 / 16,7232 / 16,7184 ms. Essas amostras foram válidas;
a medição anterior à correção de apoio também foi preservada no relatório.
O intervalo inclui a espera do limitador. Dados e intervalos brutos em
[frame-time-limited-2026-11-25.json](qa/frame-time-limited-2026-11-25.json).

Reproduzir com `tools/benchmark.py --seconds 60 --warmup-seconds 5 --fps-cap 60 --particles 500 --profile --output caminho.json`.
O checkpoint usa os mesmos instrumentos, sem alterar seu código de gameplay.

Na etapa 3, o protocolo acrescenta **uncapped no pior cenário solicitado**:
Custódio na fase 3, 20 inimigos, 500 partículas, 60 s após 5 s de warmup.

| Build OFF | FPS medido | Mediana / p95 em ms |
| --- | --- | --- |
| Checkpoint pré-Ultrakill repetido | 240,63 | 3,4218 / 7,2286 |
| Etapa 2 | 240,12 | 3,4843 / 7,0055 |
| Etapa 3 | 252,80 | 3,3827 / 6,6347 |
| Etapa 3 com cap de 60 Hz | 60,01 | 16,6646 / 16,7629 |

A mediana uncapped variou **−0,0391 ms**, e os FPS **+5,06%** contra o
checkpoint repetido. A amostra está na faixa histórica de 214–260 FPS.
Todas foram válidas, sem minimização. O cap confirma a meta de 60 Hz na
cena testada; não prova custo zero abaixo dela. O ensaio sem cap observa
o headroom nesta máquina, sem estabelecer equivalência causal a partir
de uma execução por versão. O candidato anterior à correção do salto legado
marcou 235,01 FPS e também foi preservado. A correção está no caminho ON;
não há evidência para atribuir a variação do OFF a ela.
As cenas capped das etapas 1/2 eram comuns;
a nova execução capped também inclui o chefe final.

Resumo e intervalos brutos em [stage3-frame-time-2026-11-25.json](qa/stage3-frame-time-2026-11-25.json).
Reproduzir com `tools/benchmark.py --seconds 60 --warmup-seconds 5 --final-boss --enemies 20 --particles 500 --profile --output caminho.json`,
adicionando `--fps-cap 60` para o teste capped. Não usar os ensaios com
flight recorder como baseline de FPS.

## Limites e próximas etapas

As três etapas foram implementadas. A integração com lock-on e save foi
testada; isso não certifica o balanceamento dos encontros.

Chefes ainda não foram balanceados com ON/OFF. As tabelas de HP, dano e
resistência foram preservadas. Testes de inputs simulados não certificam
gamepad físico. A 1.0 continua tendo teclado e mouse como alvo validado.
Métricas subjetivas de dificuldade exigem um playthrough real; nenhum
resultado de QA sintético é apresentado como uma partida manual.
