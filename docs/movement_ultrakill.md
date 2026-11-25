# Movimento Ágil — etapas 1 e 2 experimentais

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
| Ataque de slide | 9 / 5 / 20 | Windup / ativo / recovery, 18 stamina, pacote do leve da arma |
| Salto de slide | Impulso vertical de 7 m/s | 12 stamina, horizontal atual × 1,2 por até 24 passos |

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
Seu deslocamento desacelera linearmente. O salto básico só existe no modo
experimental; não inclui wall jump, coyote time ou jump buffer nesta etapa.

## Colisão e arquitetura

O domínio é `player/advanced_movement.py`, com vetores puros, interfaces de
`core/protocols.py`, timers inteiros e eventos. Nenhuma chamada de áudio ou
Panda3D entra nesse módulo. Input mantém remapeamento de teclado e gamepad;
com OFF, as três ações novas são filtradas antes de entrar na fila.

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

## Limites e próximas etapas

Momentum geral, coyote time e jump buffer continuam na etapa 3 e exigem
confirmação. O impulso específico do salto de slide não equivale ao sistema
geral de momentum. A integração básica com lock-on e save foi testada; isso
não certifica o balanceamento dos encontros.

Chefes ainda não foram balanceados com ON/OFF. As tabelas de HP, dano e
resistência foram preservadas. Testes de inputs simulados não certificam
gamepad físico. A 1.0 continua tendo teclado e mouse como alvo validado.
Métricas subjetivas de dificuldade exigem um playthrough real; nenhum
resultado de QA sintético é apresentado como uma partida manual.
