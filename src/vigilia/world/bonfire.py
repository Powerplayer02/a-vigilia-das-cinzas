"""Checkpoints e comandos de progressão publicados por eventos."""

from dataclasses import dataclass

from vigilia.core.events import BonfireRestedEvent, EventBus, LevelUpRequestedEvent, SaveRequestedEvent
from vigilia.core.mathx import Vec3
from vigilia.model.world_state import WorldState


@dataclass(frozen=True, slots=True)
class Bonfire:
    id: str
    name: str
    position: Vec3


BONFIRES = {
    "ruinas_cripta": Bonfire("ruinas_cripta", "Cripta da Vigília", Vec3(180, -10, 1.02)),
    "ruinas_elevador": Bonfire("ruinas_elevador", "Elevador das Memórias", Vec3(180, 30, 1.02)),
    "forno_limiar": Bonfire("forno_limiar", "Limiar da Última Chama", Vec3(240, -10, 1.02)),
    "patio_sul": Bonfire("patio_sul", "Vigília Sul", Vec3(0, -6.5, 1.02)),
    "patio_norte": Bonfire("patio_norte", "Portão Norte", Vec3(0, 9.2, 1.02)),
    "catedral_nave": Bonfire("catedral_nave", "Nave Submersa", Vec3(60, -10, 1.02)),
    "catedral_altar": Bonfire("catedral_altar", "Altar das Memórias", Vec3(69, 18, 1.02)),
    "pantano_margem": Bonfire("pantano_margem", "Margem das Cinzas", Vec3(120, -10, 1.02)),
}


class BonfireService:
    def __init__(self, state: WorldState, bus: EventBus) -> None:
        self.state, self._bus = state, bus

    def nearby(self, position: Vec3) -> Bonfire | None:
        return next((fire for fire in BONFIRES.values()
                     if (fire.position - position).length() < 2.4), None)

    def rest(self, position: Vec3) -> None:
        fire = self.nearby(position)
        if fire is None:
            raise ValueError("Aproxime-se de uma fogueira para descansar.")
        self._activate(fire)

    def travel(self, position: Vec3) -> None:
        """Alterna entre as fogueiras que já foram ativadas."""
        if self.nearby(position) is None:
            raise ValueError("O teleporte parte de uma fogueira.")
        discovered = [fire for fire in BONFIRES.values() if fire.id in self.state.visited_bonfires]
        if len(discovered) < 2:
            raise ValueError("Descanse na fogueira norte para liberar o teleporte.")
        nearest = self.nearby(position)
        target = discovered[(discovered.index(nearest) + 1) % len(discovered)]
        self._activate(target)

    def request_level_up(self, position: Vec3, attribute: str) -> None:
        fire = self.nearby(position)
        if fire is None or fire.id not in self.state.visited_bonfires:
            raise ValueError("Suba de nível em uma fogueira ativada.")
        self._bus.publish(LevelUpRequestedEvent(fire.id, attribute))

    def return_to_checkpoint(self) -> None:
        """Reinicia o exercício no último checkpoint ativado."""
        self._activate(BONFIRES[self.state.last_bonfire])

    def _activate(self, fire: Bonfire) -> None:
        self.state.visited_bonfires.add(fire.id)
        self.state.last_bonfire = fire.id
        self._bus.publish(BonfireRestedEvent(fire.id))
        self._bus.publish(SaveRequestedEvent(1, "bonfire"))
