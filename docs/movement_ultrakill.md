# Movimento Ágil — etapa 1 experimental

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

## Limites e próximas etapas

Wall cling/wall jump (24 passos de cling), slam (18 m/s, recovery de 8),
momentum geral (24 passos), coyote time e jump buffer (6 passos cada) ficam
nas etapas seguintes e exigem confirmação. O impulso específico do salto
de slide não equivale à implementação do sistema geral de momentum.

Chefes ainda não foram balanceados com ON/OFF. As tabelas de HP, dano e
resistência foram preservadas. Testes de inputs simulados não certificam
gamepad físico. A 1.0 continua tendo teclado e mouse como alvo validado.
Métricas subjetivas de dificuldade exigem um playthrough real; nenhum
resultado de QA sintético é apresentado como uma partida manual.
