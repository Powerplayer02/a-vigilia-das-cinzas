"""Contratos públicos de persistência, sem controladores ou adaptadores nativos."""

from dataclasses import dataclass, field

from vigilia.core.mathx import Vec3
from vigilia.model.attacks import AttackDefinition
from vigilia.model.stats import StatsBlock, ResistBlock

SNAPSHOT_VERSION = 1


@dataclass(frozen=True, slots=True)
class AttackSnapshot:
    definition: AttackDefinition
    age: int
    hit_targets: tuple[str, ...]
    victim: str | None
    aim: Vec3 | None = None
    fired: bool = False


@dataclass(frozen=True, slots=True)
class FighterSnapshot:
    weapon_id: str
    upgrade: int
    stats: StatsBlock
    resist: ResistBlock
    hp: float
    stamina: float
    poise: float
    buildup: dict[str, float]
    active_status: dict[str, int]
    regen_delay: int
    attack: AttackSnapshot | None
    parry_step: int
    stagger_steps: int
    riposte_steps: int
    blocking: bool
    invulnerable: bool
    hit_steps: int
    stagger_cooldown_steps: int = 0
    knockdown_steps: int = 0
    riposte_hits_remaining: int = 1


@dataclass(frozen=True, slots=True)
class MotionSnapshot:
    position: Vec3
    yaw: float
    state: str
    velocity: Vec3
    dodge_direction: Vec3
    dodge_remaining: int
    dodge_total: int
    dodge_speed: float
    dodge_progress: float


@dataclass(frozen=True, slots=True)
class ControlSnapshot:
    charge: int
    combo_buffered: bool


@dataclass(frozen=True, slots=True)
class PlayerSnapshot:
    motion: MotionSnapshot
    fighter: FighterSnapshot
    controls: ControlSnapshot
    level: int
    souls: int
    bloodstain_position: Vec3 | None
    bloodstain_souls: int
    items: dict[str, int]
    upgrades: dict[str, int]
    equipped_weapon: str
    equipped_gear: tuple[str, ...]
    character_name: str = "Vesper"
    character_class: str = "warrior"
    playtime_sec: float = 0
    starting_allocation: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ActorSnapshot:
    key: str
    position: Vec3
    yaw: float
    fighter: FighterSnapshot


@dataclass(frozen=True, slots=True)
class BossSnapshot:
    id: str
    phase: int
    position: Vec3
    yaw: float
    fighter: FighterSnapshot | None
    active: bool
    intro_remaining: int
    transition_remaining: int
    death_remaining: int
    punish_cooldown: int
    grab_cooldown: int
    aoe_cooldown: int
    pause_remaining: int
    blocking_steps: int
    close_steps: int
    last_move: str
    hazard_step: int = 0


@dataclass(frozen=True, slots=True)
class AreaSnapshot:
    actors: tuple[ActorSnapshot, ...] = ()
    bosses: tuple[BossSnapshot, ...] = ()


@dataclass(frozen=True, slots=True)
class WorldSnapshot:
    discovered_areas: tuple[str, ...]
    visited_bonfires: tuple[str, ...]
    last_bonfire: str
    dead_common: tuple[str, ...]
    defeated_bosses: tuple[str, ...]
    opened_shortcuts: tuple[str, ...]
    collected_items: tuple[str, ...]
    actors: tuple[ActorSnapshot, ...]
    practice_wait: int
    respawn_remaining: int
    boss_phases: dict[str, int] = field(default_factory=dict)
    bosses: tuple[BossSnapshot, ...] = ()
    area_id: str = "patio_da_vigilia"
    dormant_areas: dict[str, AreaSnapshot] = field(default_factory=dict)
    ending: str = ""
    credits_seen: bool = False


@dataclass(frozen=True, slots=True)
class SaveSnapshot:
    version: int
    timing_version: int
    player: PlayerSnapshot
    world: WorldSnapshot
