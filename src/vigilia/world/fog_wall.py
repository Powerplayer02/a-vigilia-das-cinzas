"""Barreira física e entrada de arena conectadas por eventos."""

from vigilia.core.events import EventBus, BossArenaEnteredEvent, BossDefeatedEvent
from vigilia.core.mathx import Vec3
from vigilia.core.protocols import IObstacle
from vigilia.model.world_state import WorldState


class FogWall:
    def __init__(self, boss_id: str, area_id: str, position: Vec3, entry: Vec3,
                 collider: IObstacle, state: WorldState, bus: EventBus) -> None:
        self.boss_id, self.area_id, self.position, self.entry = boss_id, area_id, position, entry
        self.collider, self.state, self._bus = collider, state, bus
        self.in_fight = False
        bus.subscribe(BossDefeatedEvent, self._on_defeated)
        self.sync()

    @property
    def blocked(self) -> bool:
        return self.boss_id not in self.state.defeated_bosses

    def can_enter(self, position: Vec3) -> bool:
        return (self.blocked and not self.in_fight and position.y <= self.position.y + .3
                and abs(position.x - self.position.x) < 2
                and abs(position.y - self.position.y) < 2.2)

    def cross(self, position: Vec3) -> None:
        if not self.can_enter(position):
            raise ValueError("Aproxime-se da entrada da névoa.")
        self.in_fight = True
        self._bus.publish(BossArenaEnteredEvent(self.boss_id, self.area_id, self.entry))

    def _on_defeated(self, event: BossDefeatedEvent) -> None:
        if event.boss_id == self.boss_id:
            self.in_fight = False
            self.collider.set_active(False)

    def sync(self) -> None:
        self.collider.set_active(self.blocked)

    def close(self):
        self._bus.unsubscribe(BossDefeatedEvent, self._on_defeated)
