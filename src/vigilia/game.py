"""Composição dos adaptadores e sequência de simulação da arena."""

import logging
import math
import sqlite3
import json
from dataclasses import replace
from pathlib import Path

from vigilia.core.config import Config
from vigilia.core.events import (
    AreaEnteredEvent, EventBus, BonfireRestedEvent, SaveRequestedEvent, LevelUpRequestedEvent,
    BossArenaEnteredEvent, BossDefeatedEvent, MusicChangeRequestedEvent, AppStateChangedEvent,
    SfxRequestedEvent, SoulCollectedEvent, LevelUpEvent, ItemUseStartedEvent,
    SettingsChangedEvent, EndingChosenEvent, DashStartedEvent, DashTrailEvent, SlideStartedEvent,
    WallJumpStartedEvent, SlamImpactEvent,
)
from vigilia.core.mathx import Transform, Vec3, lerp_angle
from vigilia.core.timing import (
    FIXED_DT, FixedClock, TIMING_VERSION, RESPAWN_STEPS,
    TRAINING_COOLDOWN_STEPS, TRAINING_INITIAL_WAIT_STEPS,
    TARGET_SWITCH_STEPS,
)
from vigilia.core.types import Action, GameState, InputEdge, AppState
from vigilia.core.app_state import AppStateMachine, CallbackController
from vigilia.core.locale import Localizer
from vigilia.core.settings import SettingsStore
from vigilia.engine.app import ArenaApp
from vigilia.engine.config import ConfigAdapter
from vigilia.engine.camera import SpringArmCamera
from vigilia.engine.input import InputManager, InputMode
from vigilia.engine.ui import PandaUIBackend
from vigilia.engine.physics import BulletPhysicsAdapter
from vigilia.engine.physics import BulletContactVolumes
from vigilia.engine.render import ArenaRenderer
from vigilia.engine.audio import AudioBackend, AudioEventRouter
from vigilia.engine.particles import ParticleEmitter
from vigilia.engine.polish import PresentationPolish
from vigilia.entities.components import (
    LockOnTarget, BodyRef, MovementIntent, EnemyTag, NavAgentComponent, AIStateComponent,
    BossTag, AttackIntent,
)
from vigilia.entities.ecs import Entity, World
from vigilia.entities.systems import HitboxSyncSystem, MovementSystem
from vigilia.entities.archetypes import make_enemy
from vigilia.ai.ai_system import AISystem
from vigilia.ai.bosses import BossSystem, PhaseTransitionEvent
from vigilia.player.controller import PlayerController, PlayerState
from vigilia.player.state_machine import CombatController
from vigilia.player.movesets import LONGSWORD
from vigilia.player.lock_on import TargetCandidate, select_target, cycle_target
from vigilia.combat.attack import AttackKind
from vigilia.combat.events import DamageDealt, ParrySucceeded, StaggerTriggered, EntityDied, ShotFired, HealingApplied
from vigilia.combat.fighter import Fighter
from vigilia.combat.hitbox import evaluate_pose, CombatPose
from vigilia.combat.orchestrator import CombatSystem, DeathSystem, behind
from vigilia.combat.damage import resolve_damage
from vigilia.model.items import PRACTICE_SPEC, TRAINING_STATS, DUMMY_SOULS, WEAPONS, ITEM_WEIGHTS, PLAYER_WEAPON_IDS
from vigilia.model.stats import StatsBlock, ResistBlock
from vigilia.model.inventory import Inventory
from vigilia.model.progression import Progression, Bloodstain, level_cost
from vigilia.model.world_state import WorldState
from vigilia.model.snapshots import (
    SaveSnapshot, PlayerSnapshot, WorldSnapshot, ActorSnapshot, AreaSnapshot, SNAPSHOT_VERSION,
)
from vigilia.model.enemies import ENEMIES
from vigilia.model.bosses import load_boss_profile
from vigilia.save.service import SaveService
from vigilia.save.serializers import SaveFormatError, validate
from vigilia.world.bonfire import BonfireService, BONFIRES
from vigilia.world.arena import (
    BRAZIERS, SPAWN, blocks, enter_arena, nav_grid, enemy_spawns, FOG_CENTER, FOG_SIZE,
    FORGE_ENTRY, BOSS_SPAWN, SHORTCUT_CENTER, SHORTCUT_SIZE,
)
from vigilia.world.fog_wall import FogWall
from vigilia.world.shortcut import Shortcut
from vigilia.world.map_data import MapDataProvider
from vigilia.world.area import load_area, OpenGate, Passage
from vigilia.model.areas import scene_at, area_at
from vigilia.core.views import (
    VitalsView, BossView, StatusView, StatsView, StatView, ItemView, EquipmentView,
    ItemCategory, UICommand, UICommandKind,
)
from vigilia.ui.hud import HUD
from vigilia.ui.menu_router import MenuRouter
from vigilia.ui.front_router import FrontRouter
from vigilia.model.characters import CHARACTER_CLASSES, create_character, starting_inventory
from vigilia.model.spells import SPELLS
from vigilia.core.views import CharacterClassView, OptionView
from vigilia.core.views import SlotDeletionView

logger = logging.getLogger(__name__)


class Game:
    """Monta uma arena com simulação fixa e apresentação interpolada."""

    def __init__(self, app: ArenaApp, config: Config, assets: Path, *,
                 save_path: Path | None = None, enemy_count: int = 3, legacy_hud: bool = False,
                 front_end: bool = False, settings_path: Path | None = None) -> None:
        self._app = app
        self.active_area = "patio_da_vigilia"
        self._dormant_areas = {}
        self._area_data = None
        self._data_root = assets.parent / "data"
        self._regions = {key: load_area(self._data_root / "areas" / (key + ".toml"))
            for key in ("catedral_submersa", "pantano_das_cinzas", "ruinas_subterraneas", "forno_da_vigilia")}
        self._bus = EventBus()
        save_path = save_path or assets.parent / "saves" / "slot1.sqlite3"
        self.settings = SettingsStore(settings_path or save_path.with_name("settings.toml"), config,
            legacy_path=save_path.with_name("options.json"))
        config = self.settings.options.config
        self.localizer = Localizer(assets.parent / "data/locale", self.settings.options.language)
        self.active_slot, self.character_name, self.character_class, self.playtime_sec = 1, "Vesper", "warrior", 0.0
        self.starting_allocation = {}
        self._startup_frontend, self._has_session = front_end, not front_end
        self._menu_page = "pause"
        self._slot_select_mode, self._creation_slot = "load", None
        self._config_adapter = ConfigAdapter(app)
        self._bindings = config.bindings.copy()
        self.input = InputManager(config.bindings, config.gamepad)
        self._physics = BulletPhysicsAdapter(app.render.attach_new_node("physics"))
        self._clock = FixedClock()
        self._camera = SpringArmCamera(self._physics, config.mouse_sensitivity)
        self._renderer = ArenaRenderer(app, assets, config, localizer=self.localizer)
        self._audio = AudioBackend(assets)
        self._audio_events = AudioEventRouter(self._bus, self._audio, assets.parent / "data/audio/map.toml")
        self._apply_audio_options()
        self._particles = ParticleEmitter(app.render, camera=app.camera)
        self._polish = PresentationPolish(app)
        self._footstep_distance = 0.
        self._footstep_position = SPAWN
        self._world = World()
        self.progression = Progression()
        self.inventory = Inventory()
        self.world_state = WorldState()
        self._bonfires = BonfireService(self.world_state, self._bus)
        self._save = SaveService(save_path)
        self._ready = False
        self._pending_save: SaveRequestedEvent | None = None
        self._save_boundary = False
        self._ending_credits = False
        self._respawn_remaining = 0
        self._transform = Transform(SPAWN)
        self._previous = Transform(SPAWN)
        self._fighter = Fighter(0, LONGSWORD.weapon)
        self._entity = self._world.spawn(self._transform, self._fighter)
        self.map_data = MapDataProvider(self.world_state, self._transform, self._bus)
        self._boss_path = assets.parent / "data" / "bosses" / "warden.toml"
        self.boss: BossSystem | None = None
        self.music_track = ""
        self._actors: dict[str, Entity] = {"player": self._entity}
        self._player = PlayerController(self._physics.create_character(SPAWN), self._transform)
        self._world.add(self._entity, BodyRef(self._player.body), MovementIntent())
        self._enemy_count = enemy_count
        self._enemies: list[Entity] = []
        self._previous_enemies: dict[int, Transform] = {}
        self._grid = nav_grid()
        self.ai = AISystem(self._grid, self._physics, self._entity)
        self.ai.add_system(self.map_data)
        self._movement = MovementSystem()
        self._deaths = DeathSystem(self._bus)
        self._target_switch_wait = 0
        self._switch_motion = 0.0
        self._target: Entity | None = None
        self._previous_dodge = 0.0
        self._commands = CombatController(self._fighter, self._transform, self.inventory, aim_source=self._spell_aim)
        self._contacts = BulletContactVolumes(self._physics)
        self._sync = HitboxSyncSystem(self._contacts)
        self._combat = CombatSystem(self._contacts, self._physics, self._bus)
        self._poses: dict[int, CombatPose] = {}
        self._practice_target: Entity | None = None
        self._practice_wait = TRAINING_INITIAL_WAIT_STEPS
        self._feedback = ""
        self._feedback_steps = 0
        self._bus.subscribe(AreaEnteredEvent, self._on_area_entered)
        self._bus.subscribe(DamageDealt, self._on_damage)
        self._bus.subscribe(ParrySucceeded, self._on_parry)
        self._bus.subscribe(StaggerTriggered, self._on_stagger)
        self._bus.subscribe(EntityDied, self._on_death)
        self._bus.subscribe(DashStartedEvent, lambda event: self._sfx("dash", event.position))
        self._bus.subscribe(SlideStartedEvent, lambda event: self._sfx("slide", event.position))
        self._bus.subscribe(DashTrailEvent, lambda event: self._renderer.dash_trail(event.position))
        self._bus.subscribe(WallJumpStartedEvent, lambda event: self._sfx("wall_jump", event.position))
        self._bus.subscribe(SlamImpactEvent, self._on_slam_effect)
        self._bus.subscribe(BonfireRestedEvent, self._on_bonfire_rested)
        self._bus.subscribe(SaveRequestedEvent, self._on_save_requested)
        self._bus.subscribe(LevelUpRequestedEvent, self._on_level_up)
        self._bus.subscribe(ShotFired, lambda event: self._renderer.tracer(event.origin, event.end,
            color=(.25, .65, 1, 1) if event.damage_type == "magic" else (1, .65, .24, 1)))
        self._bus.subscribe(HealingApplied, self._on_healing)
        self._bus.subscribe(BossArenaEnteredEvent, self._on_boss_entered)
        self._bus.subscribe(BossDefeatedEvent, self._on_boss_defeated)
        self._bus.subscribe(PhaseTransitionEvent, self._on_phase_transition)
        self._bus.subscribe(MusicChangeRequestedEvent, self._on_music)
        self._bus.subscribe(SoulCollectedEvent, self._on_souls)
        self._bus.subscribe(LevelUpEvent, self._on_level_effect)
        self._bus.subscribe(ItemUseStartedEvent, lambda event: self._sfx("drink", self._position(event.entity_id)))
        self.queries = GameQueries(self)
        self.ui_backend = None if legacy_hud else PandaUIBackend(app, assets / "fonts" / "ui.ttf",
            localizer=self.localizer, capture_text=self.input.set_text_capture)
        self.hud = None if legacy_hud else HUD(self.ui_backend, self.queries)
        self.menus = None if legacy_hud else MenuRouter(self.ui_backend, self.input, self.queries, self.queries, self, map_query=self.map_data)
        self._renderer.set_legacy_hud(legacy_hud, font=self.ui_backend.font if self.ui_backend else None)
        self.front = None if legacy_hud else FrontRouter(self.ui_backend, self.queries, self, self.input, navigator=self.menus)
        self.flow = AppStateMachine(self._bus)
        self.flow.register(AppState.PLAYING, CallbackController(on_enter=lambda previous: self._resume_presentation()))
        self.flow.register(AppState.PAUSED, CallbackController(
            on_enter=lambda previous: self.menus.open(self._menu_page) if self.menus else None,
            on_exit=lambda following: self.menus.close() if self.menus else None,
            on_tick=lambda dt: self.menus.tick(dt) if self.menus else None))
        for state in (AppState.MAIN_MENU, AppState.CHARACTER_CREATION, AppState.SLOT_SELECT, AppState.OPTIONS, AppState.CREDITS):
            self.flow.register(state, CallbackController(
                on_enter=lambda previous, state=state: self.front.show(state) if self.front else None,
                on_exit=lambda following: self.front.close() if self.front else None,
                on_tick=lambda dt: self.front.tick(dt) if self.front else None))
        self._bus.subscribe(AppStateChangedEvent, self._on_app_state_changed)
        self._bus.subscribe(SettingsChangedEvent, self._on_settings_changed)
        self._bus.publish(SettingsChangedEvent(self.settings.options, ("initial",)))

    def _on_area_entered(self, event: AreaEnteredEvent) -> None:
        logger.info("Área carregada: %s", event.area_id)
        self.world_state.discovered_areas.add(event.area_id)
        if self.boss is None or not self.boss.active:
            self._bus.publish(MusicChangeRequestedEvent(
                self._ambient_track()))
        if self._ready:
            self._bus.publish(SaveRequestedEvent(1, "area_change"))

    def start(self) -> None:
        """Carrega a arena procedural e seus alvos."""
        self._build_patio()
        self._renderer.finish_scene()
        self._ready = True
        self._bind_presentation_sources()
        self._initial_snapshot = self.build_snapshot()
        if not self._startup_frontend:
            self.load_game()
            self._save.acquire(self.active_slot)
        self._evaluate_poses()
        self._sync.sync({entity: pose.volumes for entity, pose in self._poses.items()})
        self.flow.transition(AppState.MAIN_MENU)
        if not self._startup_frontend:
            self.flow.transition(AppState.PLAYING)

    def _build_patio(self):
        for block in blocks():
            self._renderer.block(block.name, block.center, block.size, block.tint)
            if block.collision:
                self._physics.add_static_box(block.name, block.center, block.size)
        for position in BRAZIERS:
            self._renderer.brazier(position)
        enter_arena(self._world, self._bus)
        for index, (entity, (transform, _)) in enumerate(list(self._world.query(Transform, LockOnTarget))):
            transform.yaw = math.pi
            self._world.add(entity, Fighter(1, PRACTICE_SPEC.instantiate(), TRAINING_STATS))
            self._actors[f"dummy_{index}"] = entity
            self._renderer.target(entity.id, transform.position)
            self._physics.add_static_box(f"manequim-{entity.id}", transform.position,
                                         Vec3(.58, .47, 1.65), camera_collision=False)
            if self._practice_target is None:
                self._practice_target = entity
            if index > 0:
                self._world.remove(entity, LockOnTarget)
        profiles = tuple(ENEMIES[key] for key in ("cinzeiro", "rancor", "bestario"))
        for index, position in enumerate(enemy_spawns(self._enemy_count)):
            profile = profiles[index % len(profiles)]
            body = self._physics.create_character(position)
            patrol = tuple(self._grid.to_world(cell) for cell in (
                self._grid.to_cell(position), self._grid.to_cell(position + Vec3(0, -2.25)),
            ) if self._grid.walkable(cell))
            enemy = make_enemy(self._world, profile.id, position, body,
                               Fighter(1, profile.weapon.instantiate(), profile.stats), patrol)
            self._enemies.append(enemy)
            self._actors[f"patio.enemy.{index}"] = enemy
            self._previous_enemies[enemy.id] = Transform(position)
            self._renderer.enemy(enemy.id, position, profile.tint)
        profile = load_boss_profile(self._boss_path)
        boss_fighter = Fighter(1, profile.weapon.instantiate(), profile.stats)
        boss_body = self._physics.create_character(BOSS_SPAWN, radius=.72, height=3.4)
        boss_entity = self._world.spawn(
            Transform(BOSS_SPAWN, math.pi), boss_fighter, BodyRef(boss_body),
            MovementIntent(), AttackIntent(), BossTag(profile.id), LockOnTarget(),
        )
        self.boss = BossSystem(self._world, boss_entity, self._entity, profile, self._bus, BOSS_SPAWN)
        self.world_state.boss_phases[profile.id] = 1
        self.ai.add_system(self.boss)
        if profile.id in self.world_state.defeated_bosses:
            self.boss.defeated, boss_fighter.hp = True, 0
            boss_body.set_active(False)
        self._renderer.enemy(boss_entity.id, BOSS_SPAWN, (.57, .24, .08, 1), scale=1.8)
        self.fog = FogWall(profile.id, profile.arena, FOG_CENTER, FORGE_ENTRY,
                           self._physics.add_static_box("fog", FOG_CENTER, FOG_SIZE), self.world_state, self._bus)
        self.shortcut = Shortcut(SHORTCUT_CENTER,
                                  self._physics.add_static_box("shortcut", SHORTCUT_CENTER, SHORTCUT_SIZE),
                                  self.world_state, self._bus)
        self._renderer.gate("fog", FOG_CENTER, FOG_SIZE, fog=True)
        self._renderer.gate("shortcut", SHORTCUT_CENTER, SHORTCUT_SIZE)
        self._renderer.area_style((.17, .207, .25), (1., 1., 1.))
        self._renderer.boss_color((1., .48, .08, 1.))
        for passage in self._passages():
            self._renderer.passage(passage.id, passage.position)

    def _ambient_track(self):
        if self._area_data is not None:
            return self._area_data.music
        return "forge_ambient" if area_at(self._transform.position) == "forge_arena" else "patio_ambient"

    def _passages(self):
        if self._area_data is not None:
            return self._area_data.passages
        return (
            Passage("patio-cathedral", "catedral_submersa", Vec3(9, -9, 1.02), Vec3(60, -10, 1.02),
                "passage.catedral", requires_boss="warden_of_the_forge"),
            Passage("patio-ruins-lift", "ruinas_subterraneas", Vec3(-9, 3, 1.02), Vec3(170, 31, 1.02),
                "passage.lift", requires_flag="ruins_lift"),
            Passage("patio-cathedral-shortcut", "catedral_submersa", Vec3(-9, 7, 1.02), Vec3(50, 17, 1.02),
                "passage.shortcut", requires_flag="cathedral_return"),
        )

    def _near_passage(self):
        return next((p for p in self._passages() if (p.position - self._transform.position).flat().length() < 2.), None)

    def _use_passage(self, passage):
        if self.boss is not None and self.boss.active:
            raise ValueError(self.localizer.t("passage.in_fight"))
        if (self._fighter.attack is not None or self._commands.charge or self._player.dodging or self._fighter.parry_step >= 0):
            raise ValueError(self.localizer.t("action.finish"))
        if passage.requires_boss and passage.requires_boss not in self.world_state.defeated_bosses:
            raise ValueError(self.localizer.t("passage.boss_locked"))
        if passage.requires_flag and passage.requires_flag not in self.world_state.opened_shortcuts:
            raise ValueError(self.localizer.t("passage.other_side"))
        if not passage.target:
            self._notify(self.localizer.t("passage.future"))
            return
        if passage.unlock:
            self.world_state.opened_shortcuts.add(passage.unlock)
        self.change_area(passage.target, passage.arrival)

    def _capture_area(self):
        keys = self._actor_keys()
        actors = tuple(ActorSnapshot(key, self._world.get(entity, Transform).position,
            self._world.get(entity, Transform).yaw, self._world.get(entity, Fighter).to_snapshot(keys))
            for key, entity in self._actors.items() if key != "player")
        return AreaSnapshot(actors, (self.boss.to_snapshot(keys),) if self.boss is not None else ())

    def _preflight_area(self, area_id, data):
        if area_id == "patio_da_vigilia":
            expected, bosses = {f"dummy_{i}" for i in range(3)}, {"warden_of_the_forge"}
            keys = {actor.key for actor in data.actors}
            npc_keys = {key for key in keys if key.startswith("patio.enemy.")}
            if npc_keys and npc_keys != {f"patio.enemy.{i}" for i in range(len(npc_keys))}:
                raise SaveFormatError("Catálogo de inimigos do Pátio inválido.")
            if len(npc_keys) > 20:
                raise SaveFormatError("Quantidade de inimigos do Pátio inválida.")
            expected |= npc_keys
        elif area_id in self._regions:
            definition = self._regions[area_id]
            expected = {spawn.id for spawn in definition.enemies}
            bosses = {load_boss_profile(self._data_root / "bosses" / definition.boss["profile"]).id} if definition.boss else set()
        else:
            raise SaveFormatError("Área incompatível com esta versão.")
        if {actor.key for actor in data.actors} != expected or (data.bosses and {boss.id for boss in data.bosses} != bosses):
            raise SaveFormatError("O save pertence a uma composição de área incompatível.")

    def _build_region(self, area_id, *, stress_enemies=None):
        definition = self._regions[area_id]
        self._area_data = definition
        self._grid = definition.navigation()
        self.ai.grid = self._grid
        for block in definition.blocks:
            self._renderer.block(block.name, block.center, block.size, block.tint)
            if block.collision:
                self._physics.add_static_box(block.name, block.center, block.size)
        for point in definition.fires:
            self._renderer.brazier(point)
        for passage in definition.passages:
            self._renderer.passage(passage.id, passage.position, locked=not bool(passage.target))
        self._renderer.area_style(definition.fog_color, definition.light_color)
        spawns = [(row.id, row.profile, row.position) for row in definition.enemies]
        if stress_enemies is not None:
            points = []
            min_x, min_y, max_x, max_y = load_boss_profile(self._data_root / "bosses" / definition.boss["profile"]).bounds
            for y, row in enumerate(self._grid.cells):
                for x, free in enumerate(row):
                    point = self._grid.to_world((x, y))
                    if (free and min_x+1 < point.x < max_x-1 and min_y+2 < point.y < max_y-2 and
                            all((point - other).flat().length() > 2. for other in points)):
                        points.append(point)
            if stress_enemies > len(points):
                raise ValueError("Não há células livres suficientes para o estresse.")
            spawns = [(f"stress.{i}", ("salt_guard", "ossuary_acolyte", "bog_ghoul")[i % 3], point)
                for i, point in enumerate(points[:stress_enemies])]
        for key, profile_id, point in spawns:
            profile = ENEMIES[profile_id]
            fighter = Fighter(1, profile.weapon.instantiate(), profile.stats, resist=profile.resist)
            body = self._physics.create_character(point)
            patrol = tuple(self._grid.to_world(cell) for cell in (self._grid.to_cell(point),
                self._grid.to_cell(point + Vec3(0, 1.5))) if self._grid.walkable(cell))
            entity = make_enemy(self._world, profile_id, point, body, fighter, patrol)
            self._actors[key] = entity
            self._enemies.append(entity)
            self._previous_enemies[entity.id] = Transform(point)
            self._renderer.enemy(entity.id, point, profile.tint)
        self.fog, self.shortcut = OpenGate(self.world_state), OpenGate(self.world_state)
        if definition.boss:
            self._boss_path = self._data_root / "bosses" / definition.boss["profile"]
            profile = load_boss_profile(self._boss_path)
            point = Vec3(*definition.boss["spawn"])
            fighter = Fighter(1, profile.weapon.instantiate(), profile.stats,
                resist=ResistBlock(physical_slash=8, physical_strike=3, physical_pierce=8, magic=20, fire=-10))
            body = self._physics.create_character(point, radius=.72, height=3.4)
            entity = self._world.spawn(Transform(point, math.pi), fighter, BodyRef(body), MovementIntent(),
                AttackIntent(), BossTag(profile.id), LockOnTarget())
            self.boss = BossSystem(self._world, entity, self._entity, profile, self._bus, point, hazard_sink=self._combat.queue_hazard)
            self.world_state.boss_phases[profile.id] = 1
            if profile.id in self.world_state.defeated_bosses:
                self.boss.defeated, fighter.hp = True, 0
                body.set_active(False)
            self.ai.add_system(self.boss)
            self._renderer.enemy(entity.id, point, (.12, .38, .52, 1), scale=1.8)
            self._renderer.boss_color((1., .25, .03, 1.) if profile.phase3_threshold else (.15, .65, 1., 1.))
            fog = Vec3(*definition.boss["fog"])
            size = Vec3(4.1, .45, 4.7)
            self.fog = FogWall(profile.id, profile.arena, fog, Vec3(*definition.boss["entry"]),
                self._physics.add_static_box("tide-fog", fog, size), self.world_state, self._bus)
            self._renderer.gate("fog", fog, size, fog=True)

    def change_area(self, area_id, entry=None, *, stash=True, restore=True, stress_enemies=None):
        """Descarrega a cena anterior; mantém só seus contratos serializados."""
        if self._player.advanced is not None:
            self._player.advanced.cancel()
        if area_id != "patio_da_vigilia" and area_id not in self._regions:
            raise ValueError("Área indisponível.")
        if stash:
            self._dormant_areas[self.active_area] = self._capture_area()
        incoming = self._dormant_areas.pop(area_id, None) if restore else None
        if area_id == "patio_da_vigilia" and incoming is not None:
            count = sum(actor.key.startswith("patio.enemy.") for actor in incoming.actors)
            if count:
                self._enemy_count = count
        if self.boss is not None:
            self.boss.close()
        self.fog.close()
        self._physics.clear_scene(self._player.body)
        self._renderer.clear_scene()
        self._contacts.clear()
        for entity, _ in list(self._world.query(Transform, Fighter)):
            if entity != self._entity:
                self._world.destroy(entity)
        self._actors = {"player": self._entity}
        self._enemies, self._previous_enemies, self._poses = [], {}, {}
        self._practice_target, self.boss = None, None
        self._area_data = None
        self.active_area = area_id
        self._grid = nav_grid()
        self.ai = AISystem(self._grid, self._physics, self._entity)
        self.ai.add_system(self.map_data)
        if area_id == "patio_da_vigilia":
            self._boss_path = self._data_root / "bosses/warden.toml"
            self._build_patio()
        else:
            self._build_region(area_id, stress_enemies=stress_enemies)
        self._renderer.finish_scene()
        entry = entry or (SPAWN if self._area_data is None else self._area_data.spawn)
        self._player.body.teleport(entry)
        self._transform.position = entry
        self._previous = Transform(entry, self._transform.yaw)
        self._target = None
        self._camera.set_target(None)
        if incoming is not None:
            ids = {key: identity for identity, key in self._actor_keys().items()}
            for actor in incoming.actors:
                entity = self._actors[actor.key]
                pose, fighter = self._world.get(entity, Transform), self._world.get(entity, Fighter)
                pose.position, pose.yaw = actor.position, actor.yaw
                fighter.from_snapshot(actor.fighter, ids)
                body = self._world.get(entity, BodyRef)
                if body is not None:
                    body.body.teleport(pose.position)
                    body.body.set_active(fighter.alive)
            if self.boss is not None and incoming.bosses:
                data = incoming.bosses[0]
                self.boss.from_snapshot(data, ids, data.id in self.world_state.defeated_bosses)
                self._world.get(self.boss.entity, BodyRef).body.teleport(data.position)
        if self.boss is not None:
            self.world_state.boss_phases[self.boss.profile.id] = self.boss.phase
        self._deaths.reset_health(self._world)
        self._reset_enemies(restore=False)
        self._bind_presentation_sources()
        self._sync_world_geometry()
        self._evaluate_poses()
        self._sync.sync({identity: pose.volumes for identity, pose in self._poses.items()})
        self._particles.clear()
        self._polish.reset()
        self._polish.fade(.25, immediate=True)
        self.input.reset()
        self._clock.reset()
        self._bus.publish(AreaEnteredEvent(area_id))

    def keyboard(self, name: str, pressed: bool) -> None:
        """Recebe uma alteração física de tecla ou botão do mouse."""
        self.input.key(name, pressed)

    def gamepad(self, buttons: frozenset[str], x: float, y: float) -> None:
        """Recebe o snapshot do gamepad ativo."""
        self.input.poll_gamepad(buttons, x, y)

    def reset_input(self) -> None:
        """Libera comandos e mantém a pose atual ao perder o foco."""
        self.input.reset()
        self._clock.reset()
        self._previous = Transform(self._transform.position, self._transform.yaw)
        self._previous_dodge = self._player.dodge_progress

    def frame(self, elapsed: float, mouse: tuple[float, float],
              stick: tuple[float, float]) -> None:
        """Atualiza entradas, simulação e câmera antes do render do Panda3D."""
        dt = min(max(0.0, elapsed), 0.25)
        flow = getattr(self, "flow", None)
        if self.menus is not None:
            if self._app.state == GameState.PAUSED and not self.menus.opened and (flow is None or flow.simulating):
                self.open_menu()
            if request := self.input.menu_request():
                page = {Action.PAUSE: "pause", Action.OPEN_INVENTORY: "inventory",
                        Action.OPEN_STATUS: "status", Action.OPEN_LEVEL_UP: "level"}[request.action]
                self.open_menu(page)
        menu_frame = not flow.simulating if flow else self.menus is not None and self.menus.opened
        if self._app.state == GameState.PLAYING:
            self._camera.look(mouse, stick, dt)
            if self._target is not None:
                self._switch_motion += mouse[0]
                if not self._target_switch_wait:
                    if abs(stick[0]) > .65:
                        self._cycle_lock(1 if stick[0] > 0 else -1)
                    elif abs(self._switch_motion) > 35:
                        self._cycle_lock(1 if self._switch_motion > 0 else -1)
            else:
                self._switch_motion = 0
        if menu_frame:
            self._clock.reset()
            if flow is not None:
                flow.tick(dt)
            else:
                self.menus.tick(dt)
            self._flush_save()
            alpha = 1.0
        else:
            self.playtime_sec = getattr(self, "playtime_sec", 0) + dt
            alpha = self._clock.advance(dt, self._fixed_step)
        paused = self._app.state == GameState.PAUSED
        if paused:
            alpha = 1.0
        position = self._previous.position.lerp(self._transform.position, alpha)
        yaw = lerp_angle(self._previous.yaw, self._transform.yaw, alpha)
        dodge = self._player.dodge_progress
        if dodge >= self._previous_dodge:
            dodge = self._previous_dodge + (dodge - self._previous_dodge) * alpha
        pose = self._camera.update(position, 0 if paused else dt)
        direction = (pose.look_at - pose.position).flat().normalized()
        self._audio.set_listener(position, Vec3(direction.y, -direction.x))
        self._audio.update(dt)
        self._particles.update(0 if paused else dt, position)
        self._presentation_footsteps(position, paused)
        pose = self._polish.update(pose, 0 if paused else dt, paused=paused)
        self._renderer.draw(
            pose, position, yaw, self._player.velocity.length(), dodge,
            self._player.state == PlayerState.ROLLING,
            self._target.id if self._target is not None else None, paused,
            dt if not paused or (getattr(self, "front", None) and self.front.opened and not self._has_session) else 0,
        )
        for entity in self._enemies:
            transform = self._world.get(entity, Transform)
            intent = self._world.get(entity, MovementIntent)
            assert transform is not None and intent is not None
            previous = self._previous_enemies[entity.id]
            self._renderer.enemy_motion(entity.id, previous.position.lerp(transform.position, alpha),
                                         lerp_angle(previous.yaw, transform.yaw, alpha), intent.velocity.length())
        self._draw_combat()
        if getattr(self, "ui_backend", None) is not None:
            self.ui_backend.tick(dt)

    def _fixed_step(self) -> None:
        edge = self.input.next_edge()
        if edge == InputEdge(Action.PAUSE, True):
            self._app.set_paused(self._app.state == GameState.PLAYING)
            self._previous = Transform(self._transform.position, self._transform.yaw)
            self._previous_dodge = self._player.dodge_progress
            return
        if self._app.state != GameState.PLAYING:
            return

        if self._progression_command(edge):
            self._flush_save()
            return
        if self._respawn_remaining:
            self._respawn_remaining -= 1
            if self._respawn_remaining == 0:
                self._respawn()
                self._bus.publish(SaveRequestedEvent(1, "respawn"))
            self._flush_save()
            return

        if edge == InputEdge(Action.LOCK_ON, True):
            self._toggle_lock()
        if edge in (InputEdge(Action.TARGET_LEFT, True), InputEdge(Action.TARGET_RIGHT, True)):
            self._cycle_lock(1 if edge.action == Action.TARGET_RIGHT else -1)
        self._target_switch_wait = max(0, self._target_switch_wait - 1)
        self._previous = Transform(self._transform.position, self._transform.yaw)
        self._previous_dodge = self._player.dodge_progress
        forward, right = self._camera.axes(self._transform.position)
        self._commands.update(
            self.input.held(), edge, forward, dodging=self._player.dodging,
            critical=self._critical_target(),
        )
        self._practice_strike()
        self._previous_enemies = {
            entity.id: Transform(transform.position, transform.yaw)
            for entity, (transform, _) in self._world.query(Transform, EnemyTag)
        }
        self.ai.tick(self._world)
        self._combat.consume_intents(self._world)
        busy = (self._fighter.attack is not None or self._fighter.parry_step >= 0
                or self._commands.charge > 0)
        self._player.update(self.input.held(), edge, forward, right,
                            locked=self._target is not None, fighter=self._fighter, busy=busy,
                            mobility=self.inventory.mobility(self._fighter.stats))
        intent = self._world.get(self._entity, MovementIntent)
        assert intent is not None
        intent.velocity = self._player.velocity
        self._movement.apply(self._world)
        self._physics.step(FIXED_DT)
        self._movement.read_back(self._world)
        self._evaluate_poses()
        self._sync.sync({entity: pose.volumes for entity, pose in self._poses.items()})
        self._combat.resolve(self._world)
        for entity, (_, fighter) in self._world.query(Transform, Fighter):
            was_alive = fighter.alive
            fighter.tick()
            if was_alive and not fighter.alive:
                self._bus.publish(EntityDied(entity.id))
        self._deaths.tick(self._world)
        self._feedback_steps = max(0, self._feedback_steps - 1)
        self._update_target()
        self._flush_save()

    def _toggle_lock(self) -> None:
        if self._target is not None:
            self._target = None
            self._camera.set_target(None)
            return
        origin = self._transform.position + Vec3(0, 0, .43)
        forward, _ = self._camera.axes(self._transform.position)
        chosen = select_target(self._lock_candidates(), origin, forward)
        if chosen is not None:
            self._target = Entity(chosen)
            self._update_target()

    def _lock_candidates(self) -> list[TargetCandidate]:
        origin = self._transform.position + Vec3(0, 0, .43)
        candidates = []
        for entity, (transform, target) in self._world.query(Transform, LockOnTarget):
            fighter = self._world.get(entity, Fighter)
            if fighter is not None and not fighter.alive:
                continue
            focus = transform.position + Vec3(0, 0, .37)
            offset = focus - origin
            distance = offset.length()
            if distance < 18 and self._physics.raycast(origin, focus) is None:
                candidates.append(TargetCandidate(entity.id, focus))
        return candidates

    def _cycle_lock(self, direction: int) -> None:
        if self._target is None or self._target_switch_wait:
            return
        forward, _ = self._camera.axes(self._transform.position)
        chosen = cycle_target(self._lock_candidates(), self._target.id, self._transform.position,
                               forward, direction)
        if chosen is not None:
            self._target = Entity(chosen)
            self._update_target()
            self._target_switch_wait = TARGET_SWITCH_STEPS
            self._switch_motion = 0

    def _update_target(self) -> None:
        if self._target is None:
            return
        transform = self._world.get(self._target, Transform)
        fighter = self._world.get(self._target, Fighter)
        if (transform is None or fighter is None or not fighter.alive or
                (transform.position - self._transform.position).length() > 20):
            self._target = None
            self._camera.set_target(None)
        else:
            self._camera.set_target(transform.position + Vec3(0, 0, .37))

    def _evaluate_poses(self) -> None:
        self._poses = {}
        for entity, (transform, fighter) in self._world.query(Transform, Fighter):
            self._poses[entity.id] = evaluate_pose(
                transform, fighter, dodge=self._player.dodge_progress if entity == self._entity else 0,
                rolling=entity == self._entity and self._player.state == PlayerState.ROLLING,
            )
        if self._player.advanced is not None and self._player.body.crouched:
            pose = self._poses[self._entity.id]
            foot = self._transform.position.z - .89
            def lower(point):
                return Vec3(point.x, point.y, foot + (point.z - foot) * .5)
            self._poses[self._entity.id] = replace(pose,
                bones={name: lower(point) for name, point in pose.bones.items()},
                volumes={name: (lower(point), radius * .5) for name, (point, radius) in pose.volumes.items()})

    def _critical_target(self) -> tuple[int, Vec3, AttackKind] | None:
        candidates = []
        for entity, (transform, fighter) in self._world.query(Transform, Fighter):
            delta = transform.position - self._transform.position
            if fighter.team == 0 or not fighter.alive or delta.length() > 1.65:
                continue
            if self._physics.raycast(self._transform.position, transform.position) is not None:
                continue
            if fighter.riposte_steps:
                candidates.append((0, delta.length(), entity.id, delta, AttackKind.RIPOSTE))
            elif not fighter.backstab_immune and behind(self._transform, transform) and fighter.attack is None:
                candidates.append((1, delta.length(), entity.id, delta, AttackKind.BACKSTAB))
        if not candidates:
            return None
        _, _, target, delta, kind = min(candidates)
        return target, delta, kind

    def _practice_strike(self) -> None:
        if self._practice_target is None or not self._fighter.alive:
            return
        fighter = self._world.get(self._practice_target, Fighter)
        transform = self._world.get(self._practice_target, Transform)
        assert fighter is not None and transform is not None
        if not fighter.alive or fighter.stagger_steps or fighter.riposte_steps or fighter.attack is not None:
            return
        self._practice_wait = max(0, self._practice_wait - 1)
        delta = self._transform.position - transform.position
        facing = transform.forward().dot(delta.flat().normalized())
        if self._practice_wait == 0 and delta.length() < 2.3 and facing > .3:
            fighter.start(PRACTICE_SPEC.attack(AttackKind.PRACTICE))
            self._practice_wait = TRAINING_COOLDOWN_STEPS

    def _notify(self, message: str) -> None:
        self._feedback, self._feedback_steps = message, 180
        logger.info(message)

    def _on_damage(self, event: DamageDealt) -> None:
        movement = getattr(getattr(self, '_player', None), 'advanced', None)
        if event.target == self._entity.id and event.amount > 0 and movement is not None:
            movement.on_damage()
        if event.source == self._entity.id and event.remaining_hp == 0 and movement is not None:
            movement.on_kill(event.target)
        position = self._position(event.target) + Vec3(0, 0, .7)
        self._sfx(event.critical or ("hit_block" if event.blocked else "hit_flesh"), position)
        self._emit("sparks" if event.blocked else "embers" if event.damage_type == "fire" else
                   "arcane" if event.damage_type == "magic" else "blood", position)
        if event.attack_kind == "forge_grab" and hasattr(self, "_polish"):
            self._polish.shake(2, 3)
        tag = self._world.get(Entity(event.target), EnemyTag)
        label = "Você" if event.target == self._entity.id else (
            ENEMIES[tag.profile_id].name if tag is not None else f"Manequim {event.target}")
        detail = event.critical or ("bloqueio" if event.blocked else "golpe")
        self._notify(f"{label}   -{event.amount:.0f} HP   {detail}   HP {event.remaining_hp:.0f}")

    def _on_parry(self, event: ParrySucceeded) -> None:
        position = self._position(event.defender) + Vec3(0, 0, .8)
        self._sfx("parry", position)
        self._emit("sparks", position)
        self._notify("PARRY — aproxime-se e use ataque leve para riposte")

    def _on_healing(self, event: HealingApplied) -> None:
        position = self._position(event.target)
        self._emit("healing", position)
        self._sfx("healing", position)
        self._notify(self.localizer.t("spell.healed", amount=f"{event.amount:.0f}"))

    def _on_stagger(self, event: StaggerTriggered) -> None:
        self._notify("GUARDA QUEBRADA" if event.guard_broken else "STAGGER")

    def _on_death(self, event: EntityDied) -> None:
        if self._world.get(Entity(event.target), BossTag) is not None:
            self._bus.publish(MusicChangeRequestedEvent("", fade_sec=1))
            return
        if event.target == self._entity.id:
            if self._respawn_remaining:
                return
            self.progression.die(self._transform.position)
            self._respawn_remaining = RESPAWN_STEPS
            self._sfx("death_player", self._transform.position)
            if hasattr(self, "_polish"):
                self._polish.fade(.15, hold=True)
            self._notify("VOCÊ MORREU — suas almas aguardam no local da morte")
        else:
            tag = self._world.get(Entity(event.target), EnemyTag)
            if tag is not None:
                state = self._world.get(Entity(event.target), AIStateComponent)
                assert state is not None
                if state.rewarded:
                    return
                state.rewarded = True
                profile = ENEMIES[tag.profile_id]
                gained = self.progression.gain(profile.souls, self._fighter.stats)
                self._sfx("death_enemy", self._position(event.target))
                self._bus.publish(SoulCollectedEvent(self._position(event.target), gained))
                self._notify(f"{profile.name} derrotado — +{gained} almas")
                key = self._actor_keys().get(event.target)
                if key:
                    self.world_state.dead_common.add(key)
                self._bus.publish(SaveRequestedEvent(1, "enemy_death"))
                return
            key = self._actor_keys()[event.target]
            if key in self.world_state.dead_common:
                return
            self.world_state.dead_common.add(key)
            gained = self.progression.gain(DUMMY_SOULS, self._fighter.stats)
            self._sfx("death_enemy", self._position(event.target))
            self._bus.publish(SoulCollectedEvent(self._position(event.target), gained))
            self._notify(f"Manequim destruído — +{gained} almas")
        self._bus.publish(SaveRequestedEvent(1, "death"))

    def _reset_training(self) -> None:
        self._bonfires.return_to_checkpoint()

    def _respawn(self) -> None:
        checkpoint = BONFIRES[self.world_state.last_bonfire].position
        self._dormant_areas.clear()
        self.world_state.dead_common.clear()
        if scene_at(checkpoint) != self.active_area:
            self.change_area(scene_at(checkpoint), checkpoint, stash=False, restore=False)
        self._player.body.teleport(checkpoint)
        self._transform.position, self._transform.yaw = checkpoint, 0
        self._previous = Transform(checkpoint)
        for entity, (_, fighter) in self._world.query(Transform, Fighter):
            if self._world.get(entity, BossTag) is None:
                fighter.restore()
        self._reset_enemies()
        if self.boss is not None:
            self.boss.reset_on_rest()
            body = self._world.get(self.boss.entity, BodyRef)
            pose = self._world.get(self.boss.entity, Transform)
            assert body is not None and pose is not None
            body.body.teleport(pose.position)
            self.world_state.boss_phases[self.boss.profile.id] = self.boss.phase
            self.fog.in_fight = self.boss.active
            self._sync_world_geometry()
            self._bus.publish(MusicChangeRequestedEvent(self._ambient_track()))
        self._deaths.reset_health(self._world)
        self._deaths.tick(self._world)
        self.world_state.dead_common.clear()
        if self._player.advanced is not None:
            self._player.advanced.cancel()
        self._player = PlayerController(self._player.body, self._transform)
        self._bind_presentation_sources()
        if hasattr(self, "_polish"):
            self._polish.reveal(.15)
            self._particles.clear()
        self._fighter.weapon = self.inventory.weapon
        self._commands = CombatController(self._fighter, self._transform, self.inventory, aim_source=self._spell_aim)
        self._target = None
        self._commands.movement = self._player.advanced
        self._camera.set_target(None)
        self._previous_dodge = 0
        self._practice_wait = TRAINING_INITIAL_WAIT_STEPS
        self._respawn_remaining = 0
        self.input.reset()
        self._evaluate_poses()
        self._sync.sync({entity: pose.volumes for entity, pose in self._poses.items()})

    def _draw_combat(self) -> None:
        if self._player.advanced is not None:
            self._renderer.set_player_crouched(self._player.body.crouched)
            self._renderer.set_player_air_state(self._player.state.value)
        if hasattr(self._renderer, "hazard"):
            self._renderer.hazard(self.boss.hazard_position if self.boss else Vec3(),
                bool(self.boss and self.boss.hazard_visible), bool(self.boss and 90 <= self.boss.hazard_step % 360 < 150))
        info = ""
        if self.hud is None:
            fighter = self._fighter
            conditions = {"bleed": "sangramento", "poison": "veneno", "frost": "congelamento", "curse": "maldição"}
            status = ", ".join(conditions[effect.value] for effect in fighter.status.active)
            labels = {
                "ready": "Pronto", "charging": "Carregando golpe", "block": "Guarda", "parry": "Parry",
                "hit_react": "Interrompido", "death": "Derrotado", "light_1": "Leve I",
                "light_2": "Leve II", "light_3": "Leve III", "heavy": "Golpe forte",
                "running": "Ataque em corrida", "riposte": "Riposte", "backstab": "Backstab",
                "knockdown": "Derrubado",
            }
            state = labels[self._commands.state.value]
            info = (f"HP  {fighter.hp:.0f} / {fighter.max_hp:.0f}\n"
                    f"ESTAMINA  {fighter.stamina:.0f} / {fighter.stats.max_stamina:.0f}\n"
                    f"ALMAS  {self.progression.souls}   Nível {self.progression.level}\n"
                    f"{fighter.weapon.name} +{fighter.weapon.upgrade}\n"
                    f"Carga {self.inventory.equip_weight:.1f}/{fighter.stats.max_equip_load:.0f} "
                    f"({self.inventory.mobility(fighter.stats).value})\n{state}   {status}")
        targets = []
        for entity, (_, combatant) in self._world.query(Transform, Fighter):
            if self.hud is None and entity != self._entity:
                tag = self._world.get(entity, EnemyTag)
                boss_tag = self._world.get(entity, BossTag)
                label = (self.boss.profile.name if boss_tag is not None and self.boss is not None else
                         ENEMIES[tag.profile_id].name if tag is not None else f"Manequim {entity.id}")
                targets.append(f"{label}  {combatant.hp:.0f} / {combatant.max_hp:.0f}")
            pose = self._poses[entity.id]
            self._renderer.combat_pose(
                entity.id, pose.bones, axe=combatant.weapon.spec_id in ("axe", "forge_warden_weapon"),
                weapon_style="staff" if combatant.weapon.spec_id in ("tide_crosier", "ossuary_lantern") else combatant.weapon.spec_id,
                shield_equipped=entity != self._entity or "shield" in self.inventory.equipped_gear,
                alive=combatant.alive, hit=combatant.hit_steps > 0,
                telegraph=(combatant.attack is not None and
                           combatant.attack.age < combatant.attack.definition.windup),
                ranged=combatant.weapon.spec_id == "vesper_crossbow",
                knocked_down=combatant.knockdown_steps > 0,
            )
        feedback = self._feedback if self._feedback_steps else ""
        if not feedback and self._near_passage() is not None:
            passage = self._near_passage()
            feedback = self.localizer.t("context.passage", key=self._bindings[Action.INTERACT].upper(), name=self.localizer.t(passage.label))
        if not feedback and self.shortcut.can_open(self._transform.position):
            feedback = self.localizer.t("context.shortcut", key=self._bindings[Action.INTERACT].upper())
        if not feedback and self.fog.can_enter(self._transform.position):
            feedback = self.localizer.t("context.fog", key=self._bindings[Action.INTERACT].upper())
        if not feedback and self._bonfires.nearby(self._transform.position) is not None:
            keys = self._bindings
            feedback = self.localizer.t("context.bonfire", interact=keys[Action.INTERACT].upper(),
                level=keys[Action.OPEN_LEVEL_UP].upper(), upgrade=keys[Action.UPGRADE].upper(), travel=keys[Action.TRAVEL].upper())
        if self.hud is None:
            self._renderer.combat_info(info, "\n".join(targets[:6]), feedback)
        if self.active_area == "forno_da_vigilia" and (self._transform.position - Vec3(240, 35, 1.02)).flat().length() < 3:
            feedback = self.localizer.t("ending.interact", key=self._bindings[Action.INTERACT].upper())
        if not feedback and self._player.advanced is not None:
            feedback = self.localizer.t("movement.charges", count=self._player.advanced.charges)
        self._context_feedback = feedback
        if self.hud is not None:
            self.hud.tick()
        stain = self.progression.bloodstain
        self._renderer.bloodstain(stain.position if stain is not None else None)
        if self.boss is not None:
            pose = self._world.get(self.boss.entity, Transform)
            movement = self._world.get(self.boss.entity, MovementIntent)
            assert pose is not None and movement is not None
            self._renderer.enemy_motion(self.boss.entity.id, pose.position, pose.yaw, movement.velocity.length())
            self._renderer.boss_info(
                self.localizer.t("boss." + self.boss.profile.id + ".name"), self.boss.fighter.hp, self.boss.fighter.max_hp, self.boss.phase,
                self.boss.active,
                self.boss.intro_remaining / self.boss.profile.intro_steps,
                self.boss.transition_remaining > 0, pose.position, self.boss.visual_radius,
                phase_caption=self.localizer.t("boss." + self.boss.profile.id + ".phase" + str(self.boss.phase)),
            )

    def _actor_keys(self) -> dict[int, str]:
        keys = {entity.id: key for key, entity in self._actors.items()}
        if self.boss is not None:
            keys[self.boss.entity.id] = self.boss.profile.id
        return keys

    def _on_bonfire_rested(self, event: BonfireRestedEvent) -> None:
        self._respawn()
        if getattr(self, "_polish", None) is not None:
            self._polish.fade(.25, immediate=True)
        self._sfx("bonfire_rest", self._transform.position)
        self._notify(f"Descanso em {BONFIRES[event.bonfire_id].name}")

    def _on_level_up(self, event: LevelUpRequestedEvent) -> None:
        old_hp, old_stamina = self._fighter.max_hp, self._fighter.stats.max_stamina
        self._fighter.stats = self.progression.level_up(self._fighter.stats, event.attribute)
        self._fighter.hp += self._fighter.max_hp - old_hp
        self._fighter.stamina += self._fighter.stats.max_stamina - old_stamina
        self._bus.publish(LevelUpEvent(self._transform.position))
        self._notify(f"Nível {self.progression.level} — {event.attribute} +1")
        self._bus.publish(SaveRequestedEvent(1, "level_up"))

    def _on_save_requested(self, event: SaveRequestedEvent) -> None:
        # Mutações em combate só marcam o slot. O snapshot mais recente é
        # capturado após o passo, num fade, tela de morte ou menu pausado.
        if event.reason == "quit" or (getattr(self, "flow", None) and self.flow.current == AppState.QUIT):
            return
        self._pending_save = SaveRequestedEvent(getattr(self, "active_slot", 1), event.reason)
        if event.reason in {"bonfire", "area_change", "respawn", "main_menu"}:
            self._save_boundary = True
        if event.reason == "manual" and self._app.state == GameState.PLAYING:
            self._notify("Salvamento agendado para a próxima fogueira ou transição")

    def _flush_save(self) -> None:
        if getattr(self, "flow", None) and self.flow.current == AppState.QUIT:
            self._pending_save, self._save_boundary = None, False
            return
        request = self._pending_save
        if request is None:
            return
        if self._app.state == GameState.PLAYING and not getattr(self, "_save_boundary", False):
            return
        polish = getattr(self, "_polish", None)
        covered = polish is not None and request.reason in {"bonfire", "area_change", "respawn", "main_menu", "ending", "credits"}
        try:
            if covered:
                polish.cover_now()
            self._save.save(request.slot, self.build_snapshot())
            self._pending_save = None
            self._save_boundary = False
            if request.reason == "manual":
                self._notify("Progresso salvo")
        except (OSError, sqlite3.Error, ValueError) as exc:
            self._save_boundary = False
            self._notify(f"Falha ao salvar — {exc}")
        finally:
            if covered:
                polish.reveal()

    def build_snapshot(self) -> SaveSnapshot:
        """Monta jogador e mundo pelos contratos públicos dos controladores."""
        keys = self._actor_keys()
        stain = self.progression.bloodstain
        player = PlayerSnapshot(
            self._player.to_snapshot(), self._fighter.to_snapshot(keys), self._commands.to_snapshot(),
            self.progression.level, self.progression.souls, stain.position if stain else None,
            stain.souls if stain else 0, self.inventory.items.copy(), self.inventory.upgrades.copy(),
            self.inventory.equipped_weapon, self.inventory.equipped_gear,
            getattr(self, "character_name", "Vesper"), getattr(self, "character_class", "warrior"), getattr(self, "playtime_sec", 0),
            getattr(self, "starting_allocation", {}).copy(),
            getattr(self._player, "advanced", None) is not None,
        )
        state = self.world_state
        actors = []
        for key, entity in self._actors.items():
            if key == "player":
                continue
            transform = self._world.get(entity, Transform)
            fighter = self._world.get(entity, Fighter)
            assert transform is not None and fighter is not None
            actors.append(ActorSnapshot(key, transform.position, transform.yaw, fighter.to_snapshot(keys)))
        world = WorldSnapshot(
            tuple(sorted(state.discovered_areas)), tuple(sorted(state.visited_bonfires)), state.last_bonfire,
            tuple(sorted(state.dead_common)), tuple(sorted(state.defeated_bosses)),
            tuple(sorted(state.opened_shortcuts)), tuple(sorted(state.collected_items)),
            tuple(actors), self._practice_wait, self._respawn_remaining,
            state.boss_phases.copy(), (self.boss.to_snapshot(keys),) if self.boss is not None else (),
            self.active_area, self._dormant_areas.copy(), state.ending, state.credits_seen,
        )
        return SaveSnapshot(SNAPSHOT_VERSION, TIMING_VERSION, player, world)

    def load_game(self) -> bool:
        """Valida o snapshot completo e restaura o slot ativo sob seu lease."""
        acquired = False
        try:
            acquired = self._save.acquire(self.active_slot)
            snapshot = self._save.load(self.active_slot)
            if snapshot is None:
                if acquired:
                    self._save.release(self.active_slot)
                return False
            self.apply_snapshot(snapshot)
            self._notify("Progresso carregado")
            if hasattr(self, "flow") and self.flow.current == AppState.PLAYING and snapshot.world.ending and not snapshot.world.credits_seen:
                self._ending_credits = True
                self.flow.push(AppState.CREDITS)
            return True
        except (OSError, sqlite3.Error, ValueError) as exc:
            if acquired:
                self._save.release(self.active_slot)
            self._notify(f"Falha ao carregar — {exc}")
            return False

    def apply_snapshot(self, snapshot: SaveSnapshot) -> None:
        """Restaura um snapshot compatível com os atores e fogueiras desta área."""
        validate(snapshot)
        ids = {key: entity_id for entity_id, key in self._actor_keys().items()}
        target_area = snapshot.world.area_id
        self._preflight_area(target_area, AreaSnapshot(snapshot.world.actors, snapshot.world.bosses))
        for area_id, area_snapshot in snapshot.world.dormant_areas.items():
            self._preflight_area(area_id, area_snapshot)
        if not set(snapshot.world.visited_bonfires) <= BONFIRES.keys():
            raise SaveFormatError("O save pertence a uma composição de área incompatível.")
        self._dormant_areas = snapshot.world.dormant_areas.copy()
        rebuild = target_area != self.active_area
        if target_area == "patio_da_vigilia":
            count = sum(actor.key.startswith("patio.enemy.") for actor in snapshot.world.actors)
            if count:
                self._enemy_count = count
                rebuild |= len(self._enemies) != count
        if rebuild:
            self.change_area(target_area, snapshot.player.motion.position, stash=False, restore=False)
        ids = {key: entity_id for entity_id, key in self._actor_keys().items()}
        player, world = snapshot.player, snapshot.world
        self.character_name, self.character_class, self.playtime_sec = player.character_name, player.character_class, player.playtime_sec
        self.starting_allocation = player.starting_allocation.copy()
        stain = Bloodstain(player.bloodstain_position, player.bloodstain_souls) if player.bloodstain_position else None
        self.progression = Progression(player.level, player.souls, stain)
        self.inventory = Inventory(player.items.copy(), player.upgrades.copy(),
                                   player.equipped_weapon, player.equipped_gear)
        self.world_state = WorldState(
            set(world.discovered_areas), set(world.visited_bonfires), world.last_bonfire,
            set(world.dead_common), set(world.defeated_bosses), set(world.opened_shortcuts),
            set(world.collected_items),
            dict(world.boss_phases), world.ending, world.credits_seen,
        )
        self._bonfires = BonfireService(self.world_state, self._bus)
        self.map_data.state = self.world_state
        self._fighter.from_snapshot(player.fighter, ids)
        self._player.body.teleport(player.motion.position)
        self._configure_agile(player.agile_movement)
        self._player.from_snapshot(player.motion)
        self._commands = CombatController(self._fighter, self._transform, self.inventory, aim_source=self._spell_aim)
        self._commands.from_snapshot(player.controls)
        self._commands.movement = self._player.advanced
        provided = {actor.key for actor in world.actors}
        for key, entity in self._actors.items():
            if key != "player" and key not in provided:
                self._world.get(entity, Fighter).restore()
                nav = self._world.get(entity, NavAgentComponent)
                if nav is not None:
                    self._world.get(entity, Transform).position = nav.home
        for actor in world.actors:
            entity = self._actors[actor.key]
            transform, fighter = self._world.get(entity, Transform), self._world.get(entity, Fighter)
            assert transform is not None and fighter is not None
            transform.position, transform.yaw = actor.position, actor.yaw
            fighter.from_snapshot(actor.fighter, ids)
        self._practice_wait, self._respawn_remaining = world.practice_wait, world.respawn_remaining
        if self.boss is not None:
            if world.bosses:
                boss_data = next((data for data in world.bosses if data.id == self.boss.profile.id), None)
                if boss_data is None:
                    raise SaveFormatError("Chefe incompatível com a área.")
                self.boss.from_snapshot(boss_data, ids, self.boss.profile.id in self.world_state.defeated_bosses)
            else:
                self.boss.defeated = False
                self.boss.fighter.restore()
                self.boss.reset_on_rest()
                if self.boss.profile.id in self.world_state.defeated_bosses:
                    self.boss.defeated, self.boss.fighter.hp = True, 0
            self.world_state.boss_phases[self.boss.profile.id] = self.boss.phase
            body = self._world.get(self.boss.entity, BodyRef)
            pose = self._world.get(self.boss.entity, Transform)
            assert body is not None and pose is not None
            body.body.teleport(pose.position)
            self.fog.state, self.shortcut.state = self.world_state, self.world_state
            self.fog.in_fight = self.boss.active
            self._sync_world_geometry()
            self._bus.publish(MusicChangeRequestedEvent(
                f"{self.boss.profile.music_prefix}_phase{self.boss.phase}" if self.boss.active else self._ambient_track()))
        self.fog.state, self.shortcut.state = self.world_state, self.world_state
        self._sync_world_geometry()
        if self.boss is None:
            self._bus.publish(MusicChangeRequestedEvent(self._ambient_track()))
        self._reset_enemies(restore=False)
        self._deaths.reset_health(self._world)
        self._deaths.tick(self._world)
        self._previous = Transform(self._transform.position, self._transform.yaw)
        self._previous_dodge = self._player.dodge_progress
        self._target = None
        self._camera.set_target(None)
        self.input.reset()
        self._pending_save = None
        self._save_boundary = False
        self._evaluate_poses()
        self._sync.sync({entity: pose.volumes for entity, pose in self._poses.items()})
        if hasattr(self, "_particles"):
            self._particles.clear()
            self._polish.reset()
            if self._respawn_remaining:
                self._polish.fade(.15, hold=True, immediate=True)

    def _reset_enemies(self, *, restore=True) -> None:
        self.ai.reset(self._world, restore=restore)
        for entity in self._enemies:
            body, nav = self._world.get(entity, BodyRef), self._world.get(entity, NavAgentComponent)
            transform = self._world.get(entity, Transform)
            assert body is not None and nav is not None and transform is not None
            body.body.teleport(nav.home if restore else transform.position)
            fighter = self._world.get(entity, Fighter)
            body.body.set_active(fighter.alive)
            self._previous_enemies[entity.id] = Transform(transform.position, transform.yaw)

    def alert_enemies(self) -> None:
        """Ativa a perseguição de todos os agentes para o ensaio de carga."""
        for _, (state,) in self._world.query(AIStateComponent):
            state.alerted = True

    def _progression_command(self, edge: InputEdge | None) -> bool:
        if edge is None or not edge.pressed:
            return False
        action = edge.action
        try:
            if action == Action.INTERACT and self.active_area == "forno_da_vigilia" and (self._transform.position - Vec3(240, 35, 1.02)).flat().length() < 3:
                if "last_ember_custodian" not in self.world_state.defeated_bosses:
                    raise ValueError(self.localizer.t("ending.locked"))
                if self.world_state.ending:
                    self._ending_credits = True
                    self.flow.push(AppState.CREDITS)
                else:
                    self.open_menu("ending")
                return True
            if action == Action.LOAD:
                self.load_game()
                return True
            if action == Action.SAVE:
                self._bus.publish(SaveRequestedEvent(1, "manual"))
                return True
            if action == Action.RELOAD_BOSS and self.boss is not None:
                self.boss.reload_profile(load_boss_profile(self._boss_path, register=False))
                body = self._world.get(self.boss.entity, BodyRef)
                pose = self._world.get(self.boss.entity, Transform)
                assert body is not None and pose is not None
                body.body.teleport(pose.position)
                self.world_state.boss_phases[self.boss.profile.id] = self.boss.phase
                self._notify("Perfil recarregado — encontro reiniciado")
                return True
            if not self._fighter.alive:
                return False
            if action == Action.RESET_ARENA:
                self._reset_training()
                return True
            if action == Action.INTERACT:
                recovered = self.progression.recover(self._transform.position)
                if recovered:
                    self._notify(f"+{recovered} almas recuperadas")
                    self._bus.publish(SoulCollectedEvent(self._transform.position, recovered))
                    self._bus.publish(SaveRequestedEvent(1, "bloodstain"))
                elif self._near_passage() is not None:
                    self._use_passage(self._near_passage())
                elif self.shortcut.can_open(self._transform.position):
                    self.shortcut.open(self._transform.position)
                    self._sync_world_geometry()
                    self._notify("Atalho do claustro aberto")
                elif self.fog.can_enter(self._transform.position):
                    self.fog.cross(self._transform.position)
                else:
                    self._bonfires.rest(self._transform.position)
                return True
            if action == Action.TRAVEL:
                self._bonfires.travel(self._transform.position)
                return True
            if action.value.startswith("level_"):
                self._bonfires.request_level_up(self._transform.position, action.value.removeprefix("level_"))
                return True
            if action == Action.UPGRADE:
                fire = self._bonfires.nearby(self._transform.position)
                if fire is None or fire.id not in self.world_state.visited_bonfires:
                    raise ValueError("Melhore armas em uma fogueira ativada.")
                if self._fighter.attack is not None:
                    raise ValueError("Conclua o ataque antes de melhorar a arma.")
                self._commands.equip(self.inventory.upgrade(self.progression))
                self._notify(f"{self._fighter.weapon.name} +{self._fighter.weapon.upgrade}")
                self._bus.publish(SaveRequestedEvent(1, "upgrade"))
                return True
        except (ValueError, OSError, KeyError, TypeError) as exc:
            self._notify(str(exc))
            return True
        return False

    def _sync_world_geometry(self) -> None:
        if self.active_area != "patio_da_vigilia":
            self.fog.sync()
            if self.boss is not None:
                self._renderer.gate_open("fog", not self.fog.blocked)
            self.ai.grid = self._area_data.navigation(fog_closed=self.fog.blocked)
            return
        self.fog.sync()
        self.shortcut.sync()
        self._renderer.gate_open("fog", not self.fog.blocked)
        self._renderer.gate_open("shortcut", self.shortcut.opened)
        self.ai.grid = nav_grid(fog_closed=self.fog.blocked, shortcut_closed=not self.shortcut.opened)

    def _on_boss_entered(self, event: BossArenaEnteredEvent) -> None:
        if self.boss is None or event.boss_id != self.boss.profile.id:
            return
        self._sfx("fog_wall_enter", event.entry)
        self._sfx("boss_roar", self._position(self.boss.entity.id))
        if hasattr(self, "_polish"):
            self._polish.fade(.3, immediate=True)
        self._player.body.teleport(event.entry)
        self._transform.position = event.entry
        self._previous = Transform(event.entry, self._transform.yaw)
        self._target = None
        self._camera.set_target(None)
        self._bus.publish(AreaEnteredEvent(event.area_id))
        self._notify(self.localizer.t("boss." + self.boss.profile.id + ".name"))

    def _on_phase_transition(self, event: PhaseTransitionEvent) -> None:
        self.world_state.boss_phases[event.boss_id] = event.phase
        position = self._position(self.boss.entity.id) if self.boss else Vec3()
        self._sfx("boss_roar", position)
        self._emit("arcane" if event.boss_id == "abbess_of_the_tide" else "boss_phase", position)
        self._notify(self.localizer.t("boss." + self.boss.profile.id + ".phase" + str(self.boss.phase)))

    def _on_boss_defeated(self, event: BossDefeatedEvent) -> None:
        if (self.boss is None or event.boss_id != self.boss.profile.id or
                event.boss_id in self.world_state.defeated_bosses):
            return
        self.world_state.defeated_bosses.add(event.boss_id)
        gained = self.progression.gain(event.souls, self._fighter.stats)
        self._sync_world_geometry()
        self._notify(f"{self.boss.profile.name} — +{gained} almas")
        if self.boss.profile.reward_item and self.boss.profile.reward_item not in self.world_state.collected_items:
            item = self.boss.profile.reward_item
            self.inventory.items[item] = 1
            self.world_state.collected_items.add(item)
        self._bus.publish(MusicChangeRequestedEvent("", fade_sec=1))
        self._sfx("boss_death", self._position(self.boss.entity.id))
        self._bus.publish(SoulCollectedEvent(self._position(self.boss.entity.id), gained))
        if hasattr(self, "_polish"):
            self._polish.shake(8, 5)
        self._bus.publish(SaveRequestedEvent(1, "boss_defeated"))

    def _on_music(self, event: MusicChangeRequestedEvent) -> None:
        self.music_track = event.track_id
        if hasattr(self, "_audio"):
            if event.track_id:
                self._audio.play_music(event.track_id, fade_sec=event.fade_sec)
            else:
                self._audio.stop_music(fade_sec=event.fade_sec)
        logger.info("Música solicitada: %s", event.track_id)

    def _on_app_state_changed(self, event: AppStateChangedEvent) -> None:
        """Único consumidor de transições da aplicação na composição nativa."""
        self._app.set_paused(not self.flow.simulating)
        self.input.set_mode(InputMode.GAMEPLAY if self.flow.simulating else InputMode.MENU, force=True)
        self._clock.reset()
        if self.hud is not None:
            self.hud.root.hide() if self.front.opened else self.hud.root.show()
        tracks = {AppState.MAIN_MENU: "menu_theme", AppState.CHARACTER_CREATION: "menu_theme",
                  AppState.SLOT_SELECT: "menu_theme", AppState.CREDITS: "menu_theme"}
        track = tracks.get(event.current)
        if self.flow.simulating:
            track = f"{self.boss.profile.music_prefix}_phase{self.boss.phase}" if self.boss is not None and self.boss.active else self._ambient_track()
        if track is not None and track != self.music_track:
            self._bus.publish(MusicChangeRequestedEvent(track))
        if event.current == AppState.QUIT:
            self._app.finish()
        if self.ui_backend is not None:
            self.ui_backend.transition()

    def _resume_presentation(self):
        self._previous = Transform(self._transform.position, self._transform.yaw)
        self._previous_dodge = self._player.dodge_progress
        self._previous_enemies = {entity.id: Transform(pose.position, pose.yaw)
            for entity, (pose, _) in self._world.query(Transform, EnemyTag)}

    def _position(self, entity_id):
        pose = self._world.get(Entity(entity_id), Transform)
        return pose.position if pose else Vec3()

    def _sfx(self, kind, position=None):
        self._bus.publish(SfxRequestedEvent(kind, position))

    def _on_slam_effect(self, event):
        self._sfx("slam", event.position)
        self._renderer.slam_wave(event.position, event.radius)

    def _emit(self, preset, position):
        if hasattr(self, "_particles"):
            self._particles.spawn(preset, position)

    def _on_souls(self, event):
        self._sfx("soul_collect", event.position)
        self._emit("souls", event.position)

    def _on_level_effect(self, event):
        self._sfx("level_up", event.position)
        self._emit("level", event.position)

    def _bind_presentation_sources(self):
        if hasattr(self, "settings"):
            self._configure_agile(self.settings.options.config.ultrakill_style)
        self._player.on_dodge = lambda: self._sfx("roll", self._transform.position)
        for entity, (_, fighter) in self._world.query(Transform, Fighter):
            fighter.on_attack = lambda definition, identity=entity.id: self._sfx(
                "cast_arcane" if definition.kind == AttackKind.ARCANE_BOLT else
                "cast_heal" if definition.kind == AttackKind.MENDING_LIGHT else
                "swing_heavy" if definition.kind in (AttackKind.HEAVY, AttackKind.SLOW_OVERHEAD, AttackKind.FORGE_GRAB)
                else "swing_light", self._position(identity))

    def _configure_agile(self, enabled):
        from vigilia.player.advanced_movement import AdvancedMovement
        current = getattr(self._player, "advanced", None)
        if not enabled and current is not None:
            if not self._player.body.set_crouched(False):
                raise ValueError("movement.blocked")
            current.cancel()
            if hasattr(self, "_renderer"):
                self._renderer.set_player_crouched(False)
                self._renderer.set_player_air_state("")
            if self._fighter.attack is not None and self._fighter.attack.definition.kind == AttackKind.SLIDING:
                self._fighter.attack = None
            if self._player.state in (PlayerState.DASHING, PlayerState.SLIDING, PlayerState.AIRBORNE,
                    PlayerState.WALL_CLING, PlayerState.SLAMMING, PlayerState.SLAM_RECOVERY):
                self._player.state, self._player.velocity = PlayerState.IDLE, Vec3()
                self._fighter.invulnerable = False
        if enabled and current is None:
            current = AdvancedMovement(self._player.body, emit=self._bus.publish, entity_id=self._entity.id,
                physics=self._physics)
            if hasattr(self, "_renderer"):
                self._renderer.prepare_agile_visuals()
        self._player.advanced = current if enabled else None
        self._commands.movement = self._player.advanced
        if hasattr(self, "settings"):
            self.input.set_agile_enabled(enabled)
            options = self.settings.options
            self.settings.options = replace(options, config=replace(options.config, ultrakill_style=enabled))

    def _spell_aim(self):
        if self._target is not None:
            target = self._world.get(self._target, Transform)
            if target is not None:
                return target.position + Vec3(0, 0, .25)
        forward, _ = self._camera.axes(self._transform.position)
        return self._transform.position + Vec3(0, 0, .25) + forward * 15

    def _presentation_footsteps(self, position, paused):
        distance = (position - self._footstep_position).flat().length()
        self._footstep_position = position
        if paused or distance > 1 or self._player.state not in (PlayerState.WALKING, PlayerState.RUNNING):
            self._footstep_distance = 0.
            return
        self._footstep_distance += distance
        if self._footstep_distance >= .85:
            self._footstep_distance %= .85
            self._sfx("footstep_heavy" if self.inventory.mobility(self._fighter.stats).value == "heavy" else "footstep_light", position)

    def _apply_audio_options(self):
        self._bus.publish(SettingsChangedEvent(self.settings.options, ("audio",)))

    def enable_diagnostics(self, directory=None, *, report_path=None):
        from vigilia.engine.diagnostics import QADiagnostics, build_fingerprint, archive_build
        build_id = build_fingerprint(self._data_root.parent)
        archive_build(self._data_root.parent, build_id)
        directory = directory or self._data_root.parent / "artifacts/spikes"
        report_path = report_path or self._data_root.parent / "artifacts/qa" / build_id / "diagnostics.json"
        monitor = QADiagnostics(self._app, directory, self._physics.diagnostic_contacts,
            lambda: dict(state=self.flow.current.value, area=self.active_area,
                boss=self.boss.profile.id if self.boss else "", phase=self.boss.phase if self.boss else 0,
                ending=self.world_state.ending, agile_movement=self._player.advanced is not None),
            build_id=build_id, report_path=report_path,
            registry_path=self._data_root.parent / "artifacts/qa" / build_id / "quarantine.json")
        for owner, name, label in ((self, "frame", "game_frame"), (self, "_fixed_step", "fixed_step"),
            (self._physics, "step", "bullet_step"), (self._physics, "raycast", "raycast"),
            (self._combat, "resolve", "combat"), (self._contacts, "overlaps", "contact_query"),
            (self._audio, "play_sfx", "audio_sfx"), (self._save, "save", "save"),
            (self, "_notify", "notification_and_logging"), (self, "change_area", "area_change")):
            monitor.wrap(owner, name, label)
        self._app.diagnostics = monitor
        return monitor

    def close(self):
        self._save.close()
        self._audio.close()

    def request_quit(self):
        if self.flow.current == AppState.QUIT:
            return
        # Fechar encerra a sessão. Apenas checkpoints/transições explícitos persistem.
        self._pending_save, self._save_boundary = None, False
        self.flow.transition(AppState.QUIT)

    def _return_main(self, argument=""):
        if self._has_session:
            self._bus.publish(SaveRequestedEvent(self.active_slot, "main_menu"))
            self._flush_save()
            if self._pending_save is not None:
                return self.localizer.t("save.failed")
        self._save.release(self.active_slot)
        self._has_session = False
        self.flow.transition(AppState.MAIN_MENU)
        return ""

    def _new_character_menu(self, argument=""):
        if not any(not row.occupied for row in self.queries.slots()):
            return self.localizer.t("slots.no_empty")
        self._slot_select_mode = "create"
        self.flow.push(AppState.SLOT_SELECT)
        return ""

    def _continue_menu(self, argument=""):
        if not self._save.list():
            return self.localizer.t("slots.missing")
        self._slot_select_mode = "load"
        self.flow.push(AppState.SLOT_SELECT)
        return ""

    def _load_selected_slot(self, argument):
        slot = int(argument)
        self._save.acquire(slot)
        try:
            snapshot = self._save.load(slot)
            if snapshot is None:
                self._save.release(slot)
                return self.localizer.t("slots.missing")
            self.apply_snapshot(snapshot)
        except Exception:
            self._save.release(slot)
            raise
        self.active_slot, self._has_session = slot, True
        self.flow.transition(AppState.PLAYING)
        self._ending_credits = bool(self.world_state.ending and not self.world_state.credits_seen)
        if self._ending_credits:
            self.flow.push(AppState.CREDITS)
        return ""

    def _create_selected_character(self, argument):
        data = json.loads(argument)
        name, stats, weapon_id = create_character(data["name"], data["class_id"], data["allocation"])
        slot = data["slot"]
        inventory = starting_inventory(data["class_id"])
        fighter = Fighter(0, inventory.equip(weapon_id, stats), stats)
        player = replace(self._initial_snapshot.player, fighter=fighter.to_snapshot(self._actor_keys()),
            items=inventory.items.copy(), upgrades=inventory.upgrades.copy(), equipped_weapon=weapon_id,
            equipped_gear=inventory.equipped_gear, starting_allocation=data["allocation"].copy(),
            character_name=name, character_class=data["class_id"], playtime_sec=0)
        snapshot = replace(self._initial_snapshot, player=player)
        self._save.acquire(slot)
        try:
            self._save.create(slot, snapshot)
        except Exception:
            self._save.release(slot)
            raise
        self.apply_snapshot(snapshot)
        self.active_slot, self._has_session = slot, True
        self.flow.transition(AppState.PLAYING)
        return ""

    def _set_option(self, argument):
        data = json.loads(argument)
        key, delta = data["key"], data.get("delta", 1)
        if "value" in data and (type(data["value"]) not in (int, float) or not math.isfinite(data["value"])):
            raise ValueError("options.invalid")
        if type(delta) is not int or delta not in (-1, 1):
            raise ValueError("options.invalid")
        options, config = self.settings.options, self.settings.options.config
        if key == "resolution":
            values = self._config_adapter.resolutions()
            current = values.index((config.width, config.height)) if (config.width, config.height) in values else -1
            width, height = values[(current + delta) % len(values)]
            self.settings.save(replace(options, config=replace(config, width=width, height=height)))
        elif key == "ultrakill_style":
            enabled = not config.ultrakill_style
            self._configure_agile(enabled)
            self.settings.set(key, enabled)
        elif key in ("vsync", "fullscreen"):
            self.settings.set(key, not getattr(config, key))
        elif key in ("shadow_quality", "draw_distance"):
            values = ("off", "low", "medium", "high") if key == "shadow_quality" else (40., 70., 100., 140.)
            current = values.index(getattr(config, key)) if getattr(config, key) in values else -1
            self.settings.set(key, values[(current + delta) % len(values)])
        elif key == "mouse_sensitivity":
            self.settings.set(key, max(.0005, min(.02, round(config.mouse_sensitivity + delta * .0005, 4))))
        elif key == "language":
            self.settings.set(key, "en_US" if options.language == "pt_BR" else "pt_BR")
        elif key in ("master_volume", "music_volume", "sfx_volume"):
            self.settings.set(key, max(0, min(1, round(data.get("value", getattr(options, key) + delta * .1), 2))))
        elif key in ("hud_scale", "shake_strength"):
            low, high, step = (.8, 1.4, .1) if key == "hud_scale" else (0., 1., .25)
            self.settings.set(key, max(low, min(high, round(data.get("value", getattr(options, key) + delta * step), 2))))
        elif key == "high_contrast":
            self.settings.set(key, not options.high_contrast)
        else:
            raise ValueError("options.invalid")
        self._bus.publish(SettingsChangedEvent(self.settings.options, (key,)))
        return self.localizer.t("options.restart_vsync" if key == "vsync" else "common.saved")

    def _rebind_option(self, argument):
        data = json.loads(argument)
        self.settings.rebind(data["action"], data["binding"], replace_conflicts=data.get("replace_conflicts", False),
            device=data.get("device", "keyboard"))
        self._bus.publish(SettingsChangedEvent(self.settings.options, ("bindings",)))
        return self.localizer.t("options.rebound")

    def _reset_options(self, category):
        if category in ("all", "controls") and not self.settings.defaults.config.ultrakill_style:
            self._configure_agile(False)
        self.settings.reset(category)
        self._bus.publish(SettingsChangedEvent(self.settings.options, ("reset", category)))
        return self.localizer.t("options.reset_done")

    def _on_settings_changed(self, event):
        options, config = event.options, event.options.config
        self._configure_agile(config.ultrakill_style)
        if self.localizer.language != options.language:
            self.localizer.set_language(options.language)
        self._config_adapter.apply(config)
        self._renderer.apply_config(config)
        self._camera.set_sensitivity(config.mouse_sensitivity)
        self._polish.set_strength(options.shake_strength)
        if self.hud is not None:
            self.hud.accessibility(options.hud_scale, options.high_contrast)
        for action, binding in config.bindings.items():
            if self._bindings.get(action) != binding:
                self.input.rebind(action, binding)
        for action in config.bindings.keys() | config.gamepad.keys():
            self.input.rebind(action, config.gamepad.get(action, ""), device="gamepad")
        self._bindings = config.bindings.copy()

    def _select_new_slot(self, argument):
        slot = int(argument)
        if slot not in (1, 2, 3) or self._save.list_slots()[slot - 1].occupied:
            raise ValueError("slots.occupied")
        if self._save.in_use(slot):
            raise ValueError("slots.in_use")
        self._creation_slot = slot
        self.flow.push(AppState.CHARACTER_CREATION)
        return ""

    def _delete_slot(self, argument):
        data = json.loads(argument)
        self._save.delete(data["slot"], expected_updated_at=data["updated_at"])
        return ""

    def _choose_ending(self, choice):
        from vigilia.model.endings import choose_ending
        if self.active_area != "forno_da_vigilia" or (self._transform.position - Vec3(240, 35, 1.02)).flat().length() >= 3:
            raise ValueError("ending.altar")
        if self.flow.current != AppState.PAUSED:
            raise ValueError("ending.altar")
        previous = self.world_state.ending
        choose_ending(self.world_state, choice)
        self._ending_credits = True
        self._bus.publish(SaveRequestedEvent(self.active_slot, "ending"))
        self._flush_save()
        if self._pending_save is not None:
            self.world_state.ending, self._ending_credits = previous, False
            raise ValueError("ending.save_failed")
        self._bus.publish(EndingChosenEvent(self.active_slot, choice))
        self.flow.transition(AppState.CREDITS)
        return ""

    def _back_from_front(self, argument=""):
        if self.flow.current == AppState.CREDITS and getattr(self, "_ending_credits", False):
            self.world_state.credits_seen = True
            self._bus.publish(SaveRequestedEvent(self.active_slot, "credits"))
            self._flush_save()
            if self._pending_save is not None:
                self.world_state.credits_seen = False
                return self.localizer.t("ending.save_failed")
            self._ending_credits = False
            self.flow.transition(AppState.PLAYING)
        else:
            self.flow.back()
        return ""

    def open_menu(self, page: str = "pause") -> None:
        if self.menus is None:
            return
        if hasattr(self, "flow"):
            self._menu_page = page
            self.flow.push(AppState.PAUSED)
            return
        self._app.set_paused(True)
        self.input.set_mode(InputMode.MENU)
        self._clock.reset()
        self.menus.open(page)

    def execute(self, command: UICommand) -> str:
        """Valida comandos da UI no domínio e captura autosave ainda durante a pausa."""
        if hasattr(self, "flow"):
            handlers = {
                UICommandKind.NEW_GAME: self._new_character_menu,
                UICommandKind.CONTINUE: self._continue_menu,
                UICommandKind.LOAD_SLOT: self._load_selected_slot,
                UICommandKind.CREATE_CHARACTER: self._create_selected_character,
                UICommandKind.MAIN_MENU: self._return_main,
                UICommandKind.SET_OPTION: self._set_option,
                UICommandKind.REBIND: self._rebind_option,
                UICommandKind.RESET_OPTIONS: self._reset_options,
                UICommandKind.SELECT_NEW_SLOT: self._select_new_slot,
                UICommandKind.DELETE_SLOT: self._delete_slot,
                UICommandKind.OPEN_OPTIONS: lambda arg: self.flow.push(AppState.OPTIONS),
                UICommandKind.OPEN_CREDITS: lambda arg: self.flow.push(AppState.CREDITS),
                UICommandKind.BACK: self._back_from_front,
                UICommandKind.CHOOSE_ENDING: self._choose_ending,
                UICommandKind.QUIT: lambda arg: self.request_quit(),
                UICommandKind.RESUME: lambda arg: self.flow.transition(AppState.PLAYING),
            }
            if handler := handlers.get(command.kind):
                try:
                    return handler(command.argument) or ""
                except (ValueError, OSError, sqlite3.Error, KeyError) as exc:
                    return self.localizer.t("common.error", error=self.localizer.t(str(exc)))
        if command.kind == UICommandKind.RESUME:
            if self.menus is not None:
                self.menus.close()
            self.input.set_mode(InputMode.GAMEPLAY)
            self._clock.reset()
            self._previous = Transform(self._transform.position, self._transform.yaw)
            self._previous_dodge = self._player.dodge_progress
            self._previous_enemies = {entity.id: Transform(pose.position, pose.yaw)
                for entity, (pose, _) in self._world.query(Transform, EnemyTag)}
            self._app.set_paused(False)
            return ""
        try:
            if not self._fighter.alive:
                raise ValueError("action.wait_respawn")
            if self._fighter.attack is not None or self._fighter.parry_step >= 0 or self._commands.charge or self._player.dodging:
                raise ValueError("action.finish")
            if command.kind == UICommandKind.EQUIP:
                self._commands.equip(self.inventory.equip(command.argument, self._fighter.stats))
                message = self.localizer.t("action.equipped", weapon=self.localizer.t("item." + self._fighter.weapon.spec_id))
                self._bus.publish(SaveRequestedEvent(1, "equipment"))
            elif command.kind == UICommandKind.LEVEL_UP:
                self._bonfires.request_level_up(self._transform.position, command.argument)
                message = self.localizer.t("level.success")
            else:
                raise ValueError("action.unknown")
            self._flush_save()
            return message
        except ValueError as exc:
            return self.localizer.t(str(exc))


STAT_LABELS = (("vigor", "Vigor"), ("endurance", "Endurance"), ("strength", "Força"),
               ("dexterity", "Destreza"), ("intelligence", "Inteligência"), ("faith", "Fé"), ("luck", "Sorte"))


class GameQueries:
    """Adaptador de domínio para os contratos somente de leitura da UI."""

    def __init__(self, game: Game):
        self.game = game

    def slots(self):
        return self.game._save.list_slots()

    def slot_selection_mode(self):
        return self.game._slot_select_mode

    def ending(self):
        return self.game.world_state.ending if self.game._has_session and self.game._ending_credits else ""

    def creation_slot(self):
        return self.game._creation_slot

    def slot_in_use(self, slot):
        return self.game._save.in_use(slot)

    def slot_deletion(self, slot):
        row = self.slots()[slot - 1]
        snapshot = self.game._save.load(slot)
        if snapshot is None:
            raise ValueError("slots.missing")
        return SlotDeletionView(slot, row.name, row.level, row.class_id, row.updated_at,
            snapshot.player.bloodstain_souls, self.slot_in_use(slot))

    def binding_conflicts(self, action, binding, device="keyboard"):
        return tuple(self.game.localizer.t("control." + other.value)
            for other in self.game.settings.conflicts(action, binding, device=device))

    def character_classes(self):
        tr = self.game.localizer.t
        return tuple(CharacterClassView(profile.id, tr("class." + profile.id + ".name"),
            tr("class." + profile.id + ".desc"), tr("item." + profile.starting_weapon),
            tuple(StatView(key, tr("stat." + key), getattr(profile.base_stats, key)) for key, _ in STAT_LABELS),
            ", ".join(tr("item." + key) for key in profile.starting_gear),
            ", ".join(tr("item." + key) for key in profile.starting_spells))
            for profile in CHARACTER_CLASSES.values())

    def option_rows(self, category):
        options, tr = self.game.settings.options, self.game.localizer.t
        config = options.config
        if category == "graphics":
            return (OptionView("resolution", tr("options.resolution"), f"{config.width} × {config.height}"),
                OptionView("fullscreen", tr("options.fullscreen"), tr("options.on" if config.fullscreen else "options.off")),
                OptionView("shadow_quality", tr("options.shadow_quality"), tr("options.shadow." + config.shadow_quality)),
                OptionView("draw_distance", tr("options.draw_distance"), f"{config.draw_distance:.0f} m"),
                OptionView("vsync", tr("options.vsync"), tr("options.on" if config.vsync else "options.off")))
        if category == "audio":
            return tuple(OptionView(key, tr("options." + key), f"{getattr(options, key) * 100:.0f}%", getattr(options, key))
                for key in ("master_volume", "music_volume", "sfx_volume"))
        if category in ("controls", "gamepad"):
            mapping = {key: config.gamepad.get(key, "") for key in config.bindings} if category == "gamepad" else config.bindings
            sensitivity = (OptionView("mouse_sensitivity", tr("options.sensitivity"), f"{config.mouse_sensitivity:.4f}"),
                OptionView("ultrakill_style", tr("options.ultrakill_style"), tr("options.on" if config.ultrakill_style else "options.off"))) if category == "controls" else ()
            return sensitivity + tuple(OptionView(action.value, tr("control." + action.value), binding.upper() if binding else tr("options.unbound"))
                for action, binding in mapping.items())
        if category == "accessibility":
            return (OptionView("hud_scale", tr("options.hud_scale"), f"{options.hud_scale * 100:.0f}%", options.hud_scale, .8, 1.4),
                OptionView("shake_strength", tr("options.shake"), f"{options.shake_strength * 100:.0f}%", options.shake_strength),
                OptionView("high_contrast", tr("options.contrast"), tr("options.on" if options.high_contrast else "options.off")))
        return (OptionView("language", tr("options.language_label"), tr("language." + options.language)),)

    def player_vitals(self) -> VitalsView:
        game, fighter = self.game, self.game._fighter
        spell = next((key for key in game.inventory.spells if SPELLS[key].can_cast(fighter.stats, fighter.weapon.spec_id)), None)
        definition = SPELLS[spell].attack if spell else None
        active = fighter.attack
        remaining = max(0, active.definition.duration - active.age) / 60 if active is not None else 0
        return VitalsView(fighter.hp, fighter.max_hp, fighter.stamina, fighter.stats.max_stamina,
            game.progression.souls, f"{game.localizer.t('item.' + fighter.weapon.spec_id)} +{fighter.weapon.upgrade}",
            quick_item="", quick_count=0,
            message=getattr(game, "_context_feedback", ""), quick_is_spell=False,
            spell_name=game.localizer.t("item." + spell) if spell else "",
            spell_hint=game._bindings.get(Action.CAST, "e").upper() if spell else "",
            quick_hint=game._bindings.get(Action.CAST, "e").upper() if spell else "",
            spell_kind="healing" if definition and definition.healing else "arcane" if spell else "",
            spell_stamina=definition.stamina if definition else 0,
            spell_remaining=remaining if spell else 0, spell_duration=active.definition.duration / 60 if active else 0,
            spell_ready=bool(spell and fighter.alive and fighter.stamina >= definition.stamina and
                not remaining and not fighter.stagger_steps and fighter.parry_step < 0 and not game._player.dodging and not game._commands.charge))

    def active_boss(self) -> BossView | None:
        boss = self.game.boss
        if boss is None or not boss.active or boss.defeated:
            return None
        return BossView(self.game.localizer.t("boss." + boss.profile.id + ".name"), boss.fighter.hp, boss.fighter.max_hp, boss.phase)

    def active_statuses(self) -> list[StatusView]:
        status = self.game._fighter.status
        icons = {"bleed": ("Sangramento", "S"), "poison": ("Veneno", "V"),
                 "frost": ("Congelamento", "G"), "curse": ("Maldição", "M")}
        output = []
        for key, (name, icon) in icons.items():
            effect = next((effect for effect in status.active.keys() | status.buildup.keys() if effect.value == key), None)
            if effect is not None and (effect in status.active or status.buildup.get(effect, 0) > 0):
                output.append(StatusView(key, name, icon, int(effect in status.active),
                    status.buildup.get(effect, 0), math.ceil(status.active.get(effect, 0) / 60)))
        return output

    def _stats(self, stats: StatsBlock, *, preview=False) -> StatsView:
        game, fighter = self.game, self.game._fighter
        fire = game._bonfires.nearby(game._transform.position)
        can_level = (fighter.alive and fire is not None and fire.id in game.world_state.visited_bonfires
                     and fighter.attack is None and fighter.parry_step < 0 and not game._commands.charge
                     and not game._player.dodging)
        names = (("physical_slash", "Corte"), ("physical_strike", "Impacto"), ("physical_pierce", "Perfuração"),
                 ("fire", "Fogo"), ("magic", "Magia"), ("holy", "Sagrado"))
        return StatsView(game.progression.level + int(preview),
            game.progression.souls - (self.next_level_cost() if preview else 0),
            tuple(StatView(key, game.localizer.t("stat." + key), getattr(stats, key)) for key, name in STAT_LABELS),
            stats.max_hp * fighter.max_hp / fighter.stats.max_hp, stats.max_stamina,
            stats.max_poise, game.inventory.equip_weight, stats.max_equip_load,
            game.localizer.t("roll." + game.inventory.mobility(stats).value),
            tuple((game.localizer.t("res." + key), getattr(fighter.resist, key) + stats.endurance * .6) for key, name in names), can_level)

    def current(self) -> StatsView:
        return self._stats(self.game._fighter.stats)

    def preview(self, attribute: str) -> StatsView:
        stats = self.game._fighter.stats
        if attribute not in dict(STAT_LABELS) or getattr(stats, attribute) >= 99:
            return self.current()
        return self._stats(replace(stats, **{attribute: getattr(stats, attribute) + 1}), preview=True)

    def next_level_cost(self) -> int:
        return level_cost(self.game.progression.level)

    def _item(self, key: str) -> ItemView:
        game, inventory, stats = self.game, self.game.inventory, self.game._fighter.stats
        if key in PLAYER_WEAPON_IDS:
            spec, upgrade = WEAPONS[key], inventory.upgrades[key]
            weapon = spec.instantiate(upgrade)
            damage = resolve_damage(spec.base, stats, weapon, StatsBlock(0, 0, 0, 0, 0, 0, 0), ResistBlock()).hp
            scaling = " / ".join(f"{game.localizer.t('stat.' + name)[:3]} {getattr(spec.scaling, name).value}" for name, label in
                (("strength", "For"), ("dexterity", "Des"), ("intelligence", "Int"), ("faith", "Fé"))
                if getattr(spec.scaling, name).value != "-") or "—"
            requirements = " / ".join(f"{game.localizer.t('stat.' + name)} {getattr(spec.requirements, name)}" for name, label in STAT_LABELS
                                        if getattr(spec.requirements, name))
            return ItemView(key, f"{game.localizer.t('item.' + key)} +{upgrade}", ItemCategory.WEAPON, inventory.items[key], spec.weight,
                damage, scaling, requirements, inventory.equipped_weapon == key, stats.meets(spec.requirements),
                game.localizer.t("item." + key + ".desc"))
        category = ItemCategory.MAGIC if key in SPELLS else ItemCategory.MATERIAL if key == "shard" else ItemCategory.GEAR
        return ItemView(key, game.localizer.t("item." + key), category, inventory.items[key], ITEM_WEIGHTS[key],
                        equipped=key in inventory.equipped_gear, description=game.localizer.t("item." + key + ".desc"))

    def items_by_category(self, category: ItemCategory) -> list[ItemView]:
        return [item for key, count in self.game.inventory.items.items() if count > 0
                for item in (self._item(key),) if category == ItemCategory.ALL or item.category == category]

    def equipped(self) -> EquipmentView:
        inventory = self.game.inventory
        return EquipmentView(self._item(inventory.equipped_weapon),
            tuple(self._item(key) for key in inventory.equipped_gear), inventory.equip_weight,
            self.game._fighter.stats.max_equip_load)
