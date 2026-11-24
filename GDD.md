# A Vigília das Cinzas

**Documento de design · Etapa 4 aceita funcionalmente · Etapa 5 em implementação**

## Conceito

RPG de ação 3D em terceira pessoa para um jogador. O reino de Vesper aprisionou a própria noite numa fornalha sob o castelo. Quando a chama começou a falhar, a corte interditou as estradas e passou a alimentar o fogo com as memórias dos mortos. O jogador é um dos últimos vigias, chamado de volta para alcançar a fornalha e decidir se ela ainda deve arder.

A campanha planejada começa no Pátio da Vigília, atravessa quatro novas regiões conectadas e termina com a decisão na fornalha e os créditos. A exploração revela atalhos, estilos de combate e versões contraditórias da história por meio de diálogos breves, inscrições e descrições de itens. A derrota ensina a ler os adversários e muda o risco da próxima travessia, quando o jogador volta para recuperar as almas perdidas.

## Mundo e campanha

| Local | Papel na campanha | Confronto ou descoberta |
| --- | --- | --- |
| **Pátio da Vigília** · hub | Primeira fogueira, treino e forja anexa com névoa e atalho persistente. | **Vigia da Fornalha**, primeiro chefe obrigatório já implementado. |
| **Catedral Submersa** · área 2 | Claustro inundado e primeira região nova da 5.3. | Fogueira e atalho que conectam a travessia ao Pântano. |
| **Pântano das Cinzas** · área 3 | Passarelas e ilhas, segunda região nova da 5.3. | Segundo chefe obrigatório; a derrota libera a passagem para a área 4. |
| **Ruínas Subterrâneas** · área 4 | Criptas e descida da 5.4, com retorno por atalho. | Exploração e ligação com o Forno. |
| **Forno da Vigília** · área 5 | Câmara final da 5.4, distinta da forja do Pátio. | Terceiro chefe, três fases e hazard ambiental; a vitória libera os três desfechos. |

Os nomes e o recorte de cinco áreas seguem o blueprint mais recente da Etapa 5 e substituem os nomes do plano inicial. As cinco regiões são jogáveis, com Vigia, Abadessa das Marés e Custódio da Última Chama. Os mini-chefes **Sentinela Oca** e **Viúva das Cinzas** ficam fora da 1.0, conforme o recorte de fechamento da 5.5.

Cada local tem uma fogueira e um marco visual que facilita a orientação. As fog walls se fecham durante o combate e desaparecem do percurso após a derrota definitiva do chefe. O mapa em tela cheia mostra a área e a posição do jogador, as regiões descobertas, as fogueiras visitadas e as ligações abertas. Portas, elevadores e escadas encurtam o caminho de retorno e ficam registrados no save.

Na fornalha, o jogador poderá **manter a chama**, conservando os caminhos e o custo das memórias; **extingui-la**, devolvendo a noite ao reino; ou **transformá-la**, encerrando o ciclo de sacrifício por uma chama repartida. As três escolhas têm epílogos distintos e persistência pós-créditos desde a 5.4. Fragmentos e diálogos opcionais darão contexto à decisão.

## Combate

- **Estamina e movimento.** Ataques, corrida, esquiva, bloqueio contra impactos e parry consomem estamina. A regeneração volta após uma pausa. A esquiva tem direção, animação e invulnerabilidade limitada a um intervalo da ação. Sem direção, o comando executa um recuo. A carga equipada define rolamento leve, médio ou pesado.
- **Ataques e defesa.** Combo leve de três golpes, ataque forte carregado, ataque em corrida e ataque em queda. O escudo reduz o dano à custa da guarda e pode ser quebrado. O parry começa com uma janela de 12 passos de simulação a 60 Hz (0,20 s) e expõe inimigos elegíveis a riposte. Backstab requer posição atrás do alvo e alcance válido. Jogador e inimigos têm poise e sofrem stagger quando a resistência à interrupção se esgota.
- **Armas.** Espada longa de combo versátil, machado de arcos pesados, katana de investidas rápidas, cajado de conjurações com recuperação longa e arco de disparos com tempo de mira. Cada golpe define preparação, atividade e recuperação. A forja na fogueira usa almas e materiais para melhorar armas.
- **Alvo e colisão.** A câmera livre tem lock-on e troca direcional entre alvos visíveis. Volumes ligados à cabeça, ao tronco e aos membros seguem a pose. Golpes consultam esses volumes na janela ativa. Um golpe atinge cada alvo uma vez por execução, salvo ataques explicitamente definidos em pulsos.
- **Dano e condições.** Corte, impacto, perfuração, fogo, magia e sagrado encontram resistências distintas. Sangramento dispara dano ao completar o acúmulo, veneno drena vida com o tempo, congelamento retarda a recuperação de estamina e maldição reduz o HP máximo até ser removida por descanso ou consumível.

## Inimigos e chefes

Inimigos usam uma FSM em Python com estados de espera, patrulha, perseguição, ataque, recuperação, stagger e morte. O A* encontra rotas na malha de navegação da área e respeita portas fechadas. Aproximação, sinais de ataque, combos e reação a golpes variam por arquétipo.

| Inimigo comum | Aviso e padrão | Abertura ou fraqueza |
| --- | --- | --- |
| Vigia de sal | Recolhe a lança e desfere duas estocadas. | Flanco exposto após a segunda. |
| Flagelante do Véu | Levanta o mangual antes de duas varridas e um impacto. | Recuperação longa após o impacto. |
| Besteiro exilado | Apoia a besta no ombro para disparar e recua durante a recarga. | Pressão durante a recarga. |
| Carniçal do lodo | Agacha antes de saltar, morde e cospe veneno. | Vulnerável a fogo. |
| Acólito do ossário | Ergue a lanterna, dispara projéteis e troca de posição. | Vulnerável a sagrado e à interrupção durante a conjuração. |
| Sentinela de cinza | Ajusta o escudo, investe e arremata com um corte. | Impacto desgasta a guarda. |

Cada chefe obrigatório tem nome apresentado ao entrar na arena, barra de vida própria, música e transições com sinal sonoro e visual. O **Vigia da Fornalha** já usa duas fases, agarrão e impacto de área. O segundo chefe, **Abadessa das Marés**, possui duas fases na 5.3; o terceiro terá três fases e hazard ambiental na 5.4. A definição numérica desses dois encontros acompanha as respectivas subentregas. Os mini-chefes da 5.5 terão espólios exclusivos e poderão ser ignorados no trajeto aos créditos.

## Progressão, descanso e save

- **Criação.** Guerreiro começa com machado e Força, Cavaleiro com espada e escudo e ênfase em Vigor, Assassino com katana e Destreza, Mago com cajado e Inteligência, Clérigo com maça, magia de cura e Fé. A criação mostra os atributos de classe e permite distribuir pontos iniciais. Os sete atributos são Vigor, Endurance, Força, Destreza, Inteligência, Fé e Sorte.
- **Progressão.** Almas concedidas por inimigos compram níveis a custo crescente. Talentos passivos liberados por marcos de exploração ou chefes dão opções como recuperação de estamina e resistência a condições. Armas, armaduras, anéis, magias, consumíveis, chaves e fragmentos são encontrados em campo ou recebidos como espólio. Há dois slots de anel e três de magia. O inventário comporta todos os itens, exibe seus pesos e calcula a penalidade de mobilidade pela carga equipada.
- **Ciclo de risco.** Descansar recupera HP, estamina e cargas de estus, restaura inimigos comuns e salva o progresso. Morrer deixa uma mancha de sangue com as almas carregadas e devolve o jogador à última fogueira. A mancha é recuperada por interação. Uma nova morte substitui a mancha anterior.
- **Persistência.** Três slots com autosave ao descansar e trocar de área, além de save manual pelo menu fora de combate. Cada slot registra personagem, posição, fogueira, mancha, inimigos comuns mortos desde o último descanso, itens coletados e estado de atalhos, chefes e epílogo.

## Apresentação e controles

Arquitetura gótica e ruínas de baixa contagem de polígonos, com texturas procedurais, neblina acinzentada, fogo âmbar e magia azul. Os rigs procedurais dirigem tanto a pose quanto os volumes de colisão. O conjunto de animações cobre locomoção com blend por velocidade, quatro direções de rolamento, recuo, ataques e finalizações, parry, bloqueio e impacto na guarda, dano, morte, uso de item, estus e interação. Partículas marcam golpes, parry, fumaça das fogueiras, coleta de almas e troca de fase dos chefes.

O menu principal tem cenário animado e música, com Novo Jogo, Continuar, Opções, Créditos e Sair. A pausa dá acesso a Status, Inventário, Equipamento, Mapa e Opções. O inventário usa grade, filtros e comparação com o item equipado. A fogueira oferece descanso, ajuste de atributos com confirmação, upgrade de armas e talentos. O HUD concentra HP, estamina, almas, arma, item rápido e condições. Sprites de ícones, barras e molduras compartilham um atlas. Menus têm foco claro, navegação por teclado e gamepad e transições curtas.

| Ação | Teclado e mouse | Gamepad estilo Xbox |
| --- | --- | --- |
| Mover e olhar | WASD e mouse | Dois analógicos |
| Ataque leve e forte carregado | Clique esquerdo e direito, respectivamente | RB e RT |
| Correr e bloquear | Shift corre com câmera livre e bloqueia com lock-on. Ctrl força a guarda em qualquer modo. | L3 para correr e LB para bloquear |
| Esquiva ou recuo | Espaço | B |
| Parry | R | LT |
| Lock-on e troca de alvo | Q e movimento lateral do mouse enquanto travado | R3 e analógico direito |
| Usar item, interagir e conjurar | E, F e C | X, A e Y |
| Pausa e inventário | Esc e Tab | Menu e View |

Os atalhos são remapeáveis. O menu de opções inclui idioma (pt-BR e inglês), resolução, sombras, distância de renderização e volumes independentes para master, música e efeitos. Cada área tem uma faixa ambiente em loop. Chefes obrigatórios têm leitmotivs próprios, e efeitos sintetizados distinguem superfícies, impactos, morte, parry, fogueira, progressão, coleta e navegação da interface.

## Escolha da engine e limites técnicos

- **Panda3D com Python 3.11 como versão mínima.** O acesso direto ao Bullet permite usar o mesmo mundo de colisão para movimento, câmera, cenário e volumes de combate. O backend OpenGL suporta GLSL para materiais e rim light. A documentação atual da Ursina lista Python 3.12+ e suporte informal ao Mac. A escolha preserva Python 3.11 e reduz camadas entre a simulação e a física. [Bullet no Panda3D](https://docs.panda3d.org/1.10/python/programming/physics/bullet/index) · [Backends gráficos](https://docs.panda3d.org/1.10/python/programming/rendering-process/supported-renderer-features) · [Requisitos da Ursina](https://www.ursinaengine.org/)
- **Apresentação e assets.** Cena 3D em Panda3D e interface própria em projeção ortográfica. Modelos primitivos texturizados, poses articuladas e áudio sintetizado com NumPy e `wave` permitem distribuir o jogo com recursos gerados junto ao projeto. Modelos e dados de área são preparados em segundo plano e incorporados à cena na thread principal. O `pygame.mixer` toca efeitos e transmite as faixas longas. [Carregamento assíncrono no Panda3D](https://docs.panda3d.org/1.10/python/programming/advanced-loading/async) · [Mixer do pygame](https://www.pygame.org/docs/ref/mixer.html)
- **SQLite.** A biblioteca padrão fornece transações para gravar personagem e mundo juntos. IDs estáveis e versão de esquema sustentam carregamento e migrações. Os três slots compartilham um banco local em `saves/`.
- **Meta de desempenho.** Simulação de combate em passo fixo de 60 Hz, geometria compacta e recálculo de rotas distribuído entre atualizações. A meta de 60 FPS com 20 inimigos ativos será medida em uma cena de referência em GTX 1050 ou integrada moderna, com resolução e preset registrados. O Panda3D disponibiliza wheels para Python 3.11 em Windows, Linux e macOS. A validação do jogo nessas plataformas incluirá OpenGL, teclado, gamepad e áudio. [Distribuições do Panda3D](https://pypi.org/project/Panda3D/#files)

## Estrutura de pastas proposta

```text
Ação e Aventura/
├── GDD.md
├── main.py
├── README.md
├── requirements.txt
├── assets/
│   ├── models/
│   ├── textures/
│   ├── ui/
│   └── audio/
├── data/
│   ├── world/
│   ├── items/
│   ├── enemies/
│   └── localization/
├── saves/
├── src/
│   └── vigilia/
│       ├── engine/
│       ├── entity/
│       ├── combat/
│       ├── ai/
│       ├── world/
│       ├── ui/
│       ├── save/
│       ├── audio/
│       ├── effects/
│       ├── shaders/
│       ├── items.py
│       └── stats.py
└── tests/
    ├── test_damage.py
    ├── test_progression.py
    ├── test_save.py
    ├── test_enemy_fsm.py
    └── test_parry.py
```

## Critérios de entrega

Uma partida nova deve permitir sair do Pátio, derrotar os três chefes em sequência, escolher um desfecho e chegar aos créditos. A verificação percorre também os dois confrontos opcionais, os atalhos e a recuperação de almas após morrer. Cada slot deve poder restaurar o estado salvo sem afetar os demais. A lógica de dano, custos de nível, round-trip do save, transições da FSM e limites da janela de parry será coberta com pytest. Os comandos de instalação, geração de assets, execução e teste serão documentados no README da entrega.

## Encontro jogável da 4.4

O primeiro encontro de chefe implementado é o **Vigia da Fornalha**, conforme o blueprint numérico aprovado na 4.4. Sua forja se conecta ao Pátio por névoa e atalho persistente. Ele tem 3200 HP, 180 de poise, três ataques na fase 1 e dois adicionais na fase 2, incluindo agarrão com derrubada e esfera de fogo expansível. Esse encontro passa a ser o primeiro dos três chefes obrigatórios. Os dois encontros restantes e o percurso até os créditos continuam como objetivo das próximas entregas.

## Decisões e recorte da 5.1

As cinco classes continuam sendo Guerreiro, Cavaleiro, Assassino, Mago e Clérigo. Seus perfis estão em `data/classes/*.toml`, com 60 pontos base e dez pontos de criação. A 5.1 entrega machado, espada, katana, cajado e maça, com movesets completos; equipamento inicial próprio; Estilhaço de brasa para Mago; e Luz reparadora para Clérigo. As magias consomem estamina e usam preparação/atividade/recuperação no mesmo combate, sem um recurso de mana separado nesta versão. A distribuição confirmada, o equipamento e a magia pertencem ao save do personagem.

A Etapa 4 está aceita funcionalmente. Controle físico fica para validação pós-1.0; a documentação e a instrumentação da cauda seguem na 5.6. O CI escolhido é GitHub Actions, com matriz Linux/macOS/Windows e testes sem janela. A execução remota aguarda o repositório. Esses resíduos não bloqueiam as subentregas de conteúdo.

Na 5.6, a instrumentação usará o método real `Game.frame` e as seções de apresentação, com correlação de pausas GC, Bullet, HUD e áudio. As hipóteses do blueprint ainda precisam de evidência: o pool atual não cresce ao atingir 500, e o HUD já atualiza propriedades por mudança de valor. Coletas anteriores foram pequenas; isso deve acompanhar o novo relatório. Amostras de py-spy devem ser coletadas e correlacionadas por timestamps aos quadros lentos, pois iniciar o sampler depois de um pico não captura retroativamente aquele quadro.


## Decisões da 5.2b

Novo Jogo escolhe um destino vazio antes da criação. Excluir personagem exige revisão e confirmação final, ambas com foco em Cancelar; a última ação é vermelha. A exclusão remove definitivamente o estado do slot ativo, inclusive almas na bloodstain, sem lixeira na interface. Uma sessão em outro processo impede excluir o slot em uso e permite remover os demais.

As opções incluem resolução/tela cheia, sombras de contato por qualidade, distância de visão, VSync no próximo boot, três volumes 80/100/70, remapeamento de teclado/mouse/gamepad com conflitos, PT-BR/inglês, HUD 80–140%, shake 0–100% e alto contraste. Reset existe por aba e global, acessível por foco; o global pede confirmação. O TOML de preferências contém só escolhas do usuário. A validação de gamepad físico permanece pós-1.0.

Conjurar é uma ação distinta de usar consumíveis e de atacar. A magia depende do catalisador equipado, usa estamina e apresenta ícone, custo e recuperação no HUD. A 5.2b fecha essas interfaces sem substituir a sequência de campanha: 5.3 com Catedral/Pântano e segundo chefe; 5.4 com Ruínas/Forno, terceiro chefe e finais; 5.5 com mini-chefes/lore; 5.6 com mapa ampliado e polimento.


## Entrega da 5.3

Catedral Submersa e Pântano das Cinzas são regiões por TOML, com geometria, luz/névoa, áudio, inimigos e fogueiras próprios. O Vigia libera o caminho inicial. O campanário abre um retorno persistente ao Pátio. A Catedral usa Vigias de sal e Acólitos do ossário; o Pântano acrescenta Carniçais do lodo com veneno. Os IDs antigos Cinzeiro/Rancor/Bestário continuam disponíveis no Pátio.

A Abadessa das Marés tem 3800 HP, 160 de poise, dois estágios e cinco movimentos, com transição abaixo de 55% de HP. Golpes do báculo, varrida e projétil formam o primeiro estágio; agarrão e esfera expansível são acrescentados no segundo. A vitória concede 3600 almas base e a Insígnia da maré, sem duplicação em descanso/load. O selo das Ruínas é o limite atual da campanha; atravessá-lo, o terceiro chefe e os finais pertencem à 5.4.

A troca de região descarrega física, atores e apresentação anteriores, mantendo um snapshot dos atores dormentes no save atômico. Fogueiras e bloodstain funcionam entre regiões. O mapa usa os dados descobertos por protocolo; magia e item rápido têm slots visuais separados. O aceite de desempenho do Pântano foi medido com 20 comuns, chefe na fase 2 e 500 partículas, acima de 55 FPS no 1% low em três amostras válidas. Minimizá-lo invalida a medição: o Panda3D dorme 100 ms por quadro nessa condição. Uma cauda de combate distinta permanece sob observação de QA.


## Entrega da 5.4

As Ruínas têm criptas, duas fogueiras e atalho de retorno ao Pátio; o Forno tem limiar, arena e altar. A derrota da Abadessa abre a entrada das Ruínas. O Custódio da Última Chama tem 5600 HP e transições abaixo de 66%/33%, com proteção de 90 passos. Na terceira fase, zonas alternadas avisam durante 90 passos e pulsam fogo em 90/110/130. O aviso usa o mesmo relógio da aplicação de dano e persiste com a luta. O render só o apresenta.

Manter, extinguir e transformar têm confirmação e epílogos PT/EN próprios. A escolha é imutável por personagem, salva antes dos créditos. O pós-créditos retorna ao mundo com vitória e recompensa preservadas. O save mantém o timer da terceira fase, a escolha e o reconhecimento dos créditos. O mapa ganhou seleção/foco de regiões; expansão e polimento completos continuam na 5.6.

A 5.4 recebeu QA nativo automatizado com diagnóstico ativo, HP/limiares de teste e teleporte declarados; balanceamento e campanha manual integral não foram certificados. A política de 24/11/2026 retira o bloqueio geral do pico histórico e mantém quarentena por build se um frame de QA acima de 200 ms reaparecer. Casos menores de I/O corrigidos não provam a causa histórica. O relatório consolidado está em artifacts/5.4/verification.json.

## Revisão de escopo — fechamento da 5.5 (24/11/2026)

O aceite da 5.4 substitui o planejamento anterior das etapas 5.5/5.6: o trabalho atual é fechar a versão existente, sem adicionar mini-chefes ou mecânicas. A 1.0 tem como alvo teclado e mouse; gamepad físico está fora dos recursos validados por decisão do usuário. O lançamento exige campanha manual com valores de produção, matriz dos três desfechos a partir de estado anterior ao chefe e CI remoto aprovado. O encerramento normal não grava; checkpoints e transições explícitas apresentam preto antes do commit. Estado detalhado em [RELEASE_STATUS.md](RELEASE_STATUS.md).
