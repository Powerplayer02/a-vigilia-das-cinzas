"""Tipos compartilhados entre a simulação e os adaptadores."""

from dataclasses import dataclass
from enum import StrEnum, auto

from vigilia.core.mathx import Vec3


class GameState(StrEnum):
    LOADING = auto()
    PLAYING = auto()
    PAUSED = auto()


class AppState(StrEnum):
    BOOT = auto()
    MAIN_MENU = auto()
    CHARACTER_CREATION = auto()
    PLAYING = auto()
    PAUSED = auto()
    SLOT_SELECT = auto()
    OPTIONS = auto()
    CREDITS = auto()
    QUIT = auto()


class Action(StrEnum):
    MOVE_FORWARD = auto()
    MOVE_BACK = auto()
    MOVE_LEFT = auto()
    MOVE_RIGHT = auto()
    RUN = auto()
    ROLL = auto()
    LOCK_ON = auto()
    PAUSE = auto()
    LIGHT = auto()
    HEAVY = auto()
    BLOCK = auto()
    PARRY = auto()
    CAST = auto()
    SWAP_WEAPON = auto()
    RESET_ARENA = auto()
    INTERACT = auto()
    SAVE = auto()
    LOAD = auto()
    RELOAD_BOSS = auto()
    OPEN_INVENTORY = auto()
    OPEN_STATUS = auto()
    OPEN_LEVEL_UP = auto()
    MENU_UP = auto()
    MENU_DOWN = auto()
    MENU_LEFT = auto()
    MENU_RIGHT = auto()
    MENU_CONFIRM = auto()
    MENU_DELETE = auto()
    MENU_BACK = auto()
    MENU_TAB_NEXT = auto()
    MENU_TAB_PREVIOUS = auto()
    TRAVEL = auto()
    UPGRADE = auto()
    LEVEL_VIGOR = auto()
    LEVEL_ENDURANCE = auto()
    LEVEL_STRENGTH = auto()
    LEVEL_DEXTERITY = auto()
    LEVEL_INTELLIGENCE = auto()
    LEVEL_FAITH = auto()
    LEVEL_LUCK = auto()
    TARGET_LEFT = auto()
    TARGET_RIGHT = auto()


class AIMode(StrEnum):
    IDLE = auto()
    PATROL = auto()
    CHASE = auto()
    REPOSITION = auto()
    ATTACK_WINDUP = auto()
    RECOVER = auto()
    STAGGERED = auto()
    DEAD = auto()


@dataclass(frozen=True, slots=True)
class InputEdge:
    """Uma alteração discreta no estado lógico de uma ação."""

    action: Action
    pressed: bool


@dataclass(frozen=True, slots=True)
class HeldState:
    """Estado contínuo combinado de teclado e analógico."""

    actions: frozenset[Action] = frozenset()
    move_x: float = 0.0
    move_y: float = 0.0


@dataclass(frozen=True, slots=True)
class RayHit:
    """Resultado de uma consulta de colisão contra cenário."""

    point: Vec3
    normal: Vec3
    distance: float


@dataclass(frozen=True, slots=True)
class VolumeRayHit:
    target: tuple[int, str]
    point: Vec3
    distance: float
