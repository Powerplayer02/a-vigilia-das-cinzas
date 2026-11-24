"""Componentes de gameplay compartilhados pela arena."""

from dataclasses import dataclass
from dataclasses import field
from vigilia.core.mathx import Vec3
from vigilia.core.types import AIMode
from vigilia.core.protocols import ICharacterBody
from vigilia.model.attacks import AttackDefinition


@dataclass(frozen=True, slots=True)
class LockOnTarget:
    """Distingue entidades que podem receber o foco da câmera."""

    priority: int = 0


@dataclass(slots=True)
class BodyRef:
    body: ICharacterBody


@dataclass(slots=True)
class MovementIntent:
    velocity: Vec3 = Vec3()


@dataclass(slots=True)
class AttackIntent:
    definition: AttackDefinition | None = None
    target: int | None = None
    aim: Vec3 | None = None


@dataclass(slots=True)
class AIStateComponent:
    mode: AIMode = AIMode.IDLE
    age: int = 0
    combo_index: int = 0
    alerted: bool = False
    rewarded: bool = False


@dataclass(slots=True)
class NavAgentComponent:
    home: Vec3
    patrol: tuple[Vec3, ...]
    route: list[Vec3] = field(default_factory=list)
    waypoint: int = 0
    patrol_index: int = 0
    next_repath: int = 0
    goal: Vec3 | None = None


@dataclass(frozen=True, slots=True)
class EnemyTag:
    profile_id: str


@dataclass(frozen=True, slots=True)
class BossTag:
    id: str
