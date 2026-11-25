"""Eventos publicados pelo gameplay e ligados aos consumidores no bootstrap."""

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar, cast, TYPE_CHECKING
if TYPE_CHECKING:
    from vigilia.core.settings import UserOptions
from vigilia.core.mathx import Vec3
from vigilia.core.types import AppState


class Event:
    """Base dos eventos síncronos do jogo."""

    __slots__ = ()


@dataclass(frozen=True, slots=True)
class AppStateChangedEvent(Event):
    previous: AppState
    current: AppState


@dataclass(frozen=True, slots=True)
class SettingsChangedEvent(Event):
    options: "UserOptions"
    changed: tuple[str, ...]


E = TypeVar("E", bound=Event)


class EventBus:
    """Despacha eventos pelo seu tipo concreto em ordem de inscrição."""

    def __init__(self) -> None:
        self._handlers: dict[type[Event], list[Callable[[Event], None]]] = defaultdict(list)

    def subscribe(self, event_type: type[E], handler: Callable[[E], None]) -> None:
        """Registra um consumidor para o tipo informado."""
        self._handlers[event_type].append(cast(Callable[[Event], None], handler))

    def publish(self, event: Event) -> None:
        """Invoca os consumidores registrados antes do envio."""
        for handler in tuple(self._handlers.get(type(event), ())):
            handler(event)

    def unsubscribe(self, event_type, handler):
        if handler in self._handlers.get(event_type, ()):
            self._handlers[event_type].remove(handler)


@dataclass(frozen=True, slots=True)
class AreaEnteredEvent(Event):
    area_id: str


@dataclass(frozen=True, slots=True)
class BonfireRestedEvent(Event):
    bonfire_id: str


@dataclass(frozen=True, slots=True)
class SaveRequestedEvent(Event):
    slot: int
    reason: str


@dataclass(frozen=True, slots=True)
class LevelUpRequestedEvent(Event):
    bonfire_id: str
    attribute: str


@dataclass(frozen=True, slots=True)
class MusicChangeRequestedEvent(Event):
    track_id: str
    fade_sec: float = 1.5


@dataclass(frozen=True, slots=True)
class BossArenaEnteredEvent(Event):
    boss_id: str
    area_id: str
    entry: Vec3


@dataclass(frozen=True, slots=True)
class BossDefeatedEvent(Event):
    boss_id: str
    souls: int


@dataclass(frozen=True, slots=True)
class ItemUseStartedEvent(Event):
    entity_id: int
    item_id: str


@dataclass(frozen=True, slots=True)
class SfxRequestedEvent(Event):
    kind: str
    position: Vec3 | None = None
    gain: float = 1.0


@dataclass(frozen=True, slots=True)
class SoulCollectedEvent(Event):
    position: Vec3
    amount: int


@dataclass(frozen=True, slots=True)
class LevelUpEvent(Event):
    position: Vec3


@dataclass(frozen=True, slots=True)
class EndingChosenEvent(Event):
    slot: int
    choice: str


@dataclass(frozen=True, slots=True)
class DashStartedEvent(Event):
    entity_id: int
    position: Vec3
    direction: Vec3


@dataclass(frozen=True, slots=True)
class DashTrailEvent(Event):
    position: Vec3


@dataclass(frozen=True, slots=True)
class SlideStartedEvent(Event):
    entity_id: int
    position: Vec3


@dataclass(frozen=True, slots=True)
class WallClingStartedEvent(Event):
    entity_id: int
    position: Vec3
    normal: Vec3


@dataclass(frozen=True, slots=True)
class WallJumpStartedEvent(Event):
    entity_id: int
    position: Vec3


@dataclass(frozen=True, slots=True)
class SlamStartedEvent(Event):
    entity_id: int
    position: Vec3


@dataclass(frozen=True, slots=True)
class SlamImpactEvent(Event):
    position: Vec3
    radius: float
    damage: float
    poise: float
    source: int | None = None
    team: int | None = None
    damage_parts: tuple[tuple[str, float], ...] = ()
