"""Porta de atalho com abertura persistente."""

from vigilia.core.events import EventBus, SaveRequestedEvent
from vigilia.core.mathx import Vec3
from vigilia.core.protocols import IObstacle
from vigilia.model.world_state import WorldState

SHORTCUT_ID = "cloister_gate"


class Shortcut:
    def __init__(self, position: Vec3, collider: IObstacle, state: WorldState, bus: EventBus) -> None:
        self.position, self.collider, self.state, self._bus = position, collider, state, bus
        self.sync()

    @property
    def opened(self) -> bool:
        return SHORTCUT_ID in self.state.opened_shortcuts

    def can_open(self, position: Vec3) -> bool:
        return not self.opened and (position - self.position).flat().length() < 2.2

    def open(self, position: Vec3) -> None:
        if not self.can_open(position):
            raise ValueError("Aproxime-se da porta do claustro.")
        self.state.opened_shortcuts.add(SHORTCUT_ID)
        self.sync()
        self._bus.publish(SaveRequestedEvent(1, "shortcut"))

    def sync(self) -> None:
        self.collider.set_active(not self.opened)
