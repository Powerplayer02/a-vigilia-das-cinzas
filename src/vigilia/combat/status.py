"""Acúmulo e duração dos quatro efeitos de condição."""

from dataclasses import dataclass, field

from vigilia.core.timing import FIXED_HZ, POISON_STEPS, FROST_STEPS
from vigilia.model.attacks import StatusEffect


@dataclass(slots=True)
class StatusStack:
    buildup: dict[StatusEffect, float] = field(default_factory=dict)
    active: dict[StatusEffect, int] = field(default_factory=dict)

    def apply(self, effect: StatusEffect, amount: float, max_hp: float) -> float:
        """Aplica acúmulo. Sangramento dispara dano imediato ao completar 100."""
        if effect in self.active:
            return 0
        self.buildup[effect] = self.buildup.get(effect, 0) + amount
        if self.buildup[effect] < 100:
            return 0
        del self.buildup[effect]
        if effect == StatusEffect.BLEED:
            return max_hp * .16
        self.active[effect] = {
            StatusEffect.POISON: POISON_STEPS,
            StatusEffect.FROST: FROST_STEPS,
            StatusEffect.CURSE: -1,
        }[effect]
        return 0

    def tick(self) -> float:
        """Avança as condições e devolve o dano periódico deste passo."""
        damage = 5 / FIXED_HZ if StatusEffect.POISON in self.active else 0
        for effect, time in tuple(self.active.items()):
            if time == 1:
                del self.active[effect]
            elif time > 1:
                self.active[effect] = time - 1
        for effect, buildup in tuple(self.buildup.items()):
            if buildup <= .12:
                del self.buildup[effect]
            else:
                self.buildup[effect] = buildup - .12
        return damage
