"""Almas, curva de níveis e recuperação da mancha de sangue."""

from dataclasses import dataclass, fields, replace

from vigilia.core.mathx import Vec3
from vigilia.model.stats import StatsBlock

STAT_NAMES = tuple(item.name for item in fields(StatsBlock))


@dataclass(frozen=True, slots=True)
class Bloodstain:
    position: Vec3
    souls: int


def level_cost(level: int) -> int:
    """Calcula o próximo nível, com coeficiente quadrático por faixa de vinte."""
    if level < 1:
        raise ValueError("Nível inválido.")
    tier = (level - 1) // 20
    return 60 + 25 * level + (3 + tier) * level * level


@dataclass(slots=True)
class Progression:
    level: int = 1
    souls: int = 0
    bloodstain: Bloodstain | None = None

    def gain(self, base: int, stats: StatsBlock) -> int:
        """Concede uma recompensa determinística modificada por Sorte."""
        amount = max(0, int(base * stats.drop_multiplier))
        self.souls += amount
        return amount

    def die(self, position: Vec3) -> None:
        """Substitui a mancha anterior, inclusive quando a nova morte carrega zero."""
        self.bloodstain = Bloodstain(position, self.souls) if self.souls else None
        self.souls = 0

    def recover(self, position: Vec3) -> int:
        """Recupera a mancha a até 1,8 m uma única vez."""
        stain = self.bloodstain
        if stain is None or (stain.position - position).length() > 1.8:
            return 0
        self.souls += stain.souls
        self.bloodstain = None
        return stain.souls

    def level_up(self, stats: StatsBlock, attribute: str) -> StatsBlock:
        """Debita o custo e incrementa um atributo validado."""
        if attribute not in STAT_NAMES:
            raise ValueError("Atributo desconhecido.")
        if getattr(stats, attribute) >= 99:
            raise ValueError("O atributo já chegou ao limite de 99.")
        cost = level_cost(self.level)
        if self.souls < cost:
            raise ValueError(f"São necessárias {cost} almas para o próximo nível.")
        result = replace(stats, **{attribute: getattr(stats, attribute) + 1})
        self.souls -= cost
        self.level += 1
        return result
