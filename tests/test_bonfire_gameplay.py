"""Regressão do saldo no caminho real de eventos do descanso."""

from vigilia.core.events import BonfireRestedEvent, EventBus, SaveRequestedEvent
from vigilia.core.mathx import Vec3
from vigilia.core.mathx import Transform
from vigilia.core.navigation import NavGrid
from vigilia.ai.ai_system import AISystem
from vigilia.combat.fighter import Fighter
from vigilia.combat.orchestrator import DeathSystem
from vigilia.engine.camera import SpringArmCamera
from vigilia.engine.input import InputManager
from vigilia.entities.ecs import World
from vigilia.entities.components import BodyRef
from vigilia.entities.systems import HitboxSyncSystem
from vigilia.game import Game
from vigilia.model.inventory import Inventory
from vigilia.model.progression import Bloodstain, Progression
from vigilia.model.world_state import WorldState
from vigilia.player.controller import PlayerController
from vigilia.world.bonfire import BONFIRES, BonfireService
from combat_fakes import PhysicsFake, ContactFake


class RestGame(Game):
    """Mantém o handler de gameplay e substitui física e apresentação por fakes."""

    def __init__(self):
        self.active_area, self._dormant_areas, self._area_data = "patio_da_vigilia", {}, None
        self.progression = Progression(souls=500, bloodstain=Bloodstain(Vec3(3, 4, 1), 120))
        self.world_state = WorldState(visited_bonfires={"patio_sul", "patio_norte"})
        self.world_state.opened_shortcuts.add("portao")
        self.world_state.defeated_bosses.add("vigia")
        self.inventory = Inventory()
        self._world = World()
        self._transform = Transform(Vec3(3, 4, 1))
        self._fighter = Fighter(0, self.inventory.weapon)
        self._fighter.hp = 10
        self._entity = self._world.spawn(self._transform, self._fighter)
        self._player = PlayerController(PhysicsFake(), self._transform)
        self._world.add(self._entity, BodyRef(self._player.body))
        self.ai = AISystem(NavGrid(((True,),), 1, Vec3()), PhysicsFake(), self._entity)
        self._enemies = []
        self.boss = None
        self._bus = EventBus()
        self._deaths = DeathSystem()
        self._camera = SpringArmCamera(PhysicsFake(), .003)
        self._sync = HitboxSyncSystem(ContactFake())
        self.input = InputManager()
        self.respawns = 0
        self.message = ""

    def _respawn(self):
        self.respawns += 1
        super()._respawn()

    def _notify(self, message):
        self.message = message


def test_rest_and_travel_preserve_500_souls_bloodstain_and_flags_before_autosave():
    game, bus = RestGame(), EventBus()
    bus.subscribe(BonfireRestedEvent, game._on_bonfire_rested)
    saved_balances = []
    bus.subscribe(SaveRequestedEvent, lambda event: saved_balances.append(game.progression.souls))
    bonfires = BonfireService(game.world_state, bus)
    stain = game.progression.bloodstain
    bonfires.rest(BONFIRES["patio_sul"].position)
    assert game.progression.souls == 500
    assert game.progression.bloodstain == stain
    bonfires.travel(BONFIRES["patio_sul"].position)
    bonfires.return_to_checkpoint()
    assert saved_balances == [500, 500, 500]
    assert game.progression.souls == 500
    assert game.respawns == 3
    assert game._fighter.hp == game._fighter.max_hp
    assert game.world_state.opened_shortcuts == {"portao"}
    assert game.world_state.defeated_bosses == {"vigia"}
