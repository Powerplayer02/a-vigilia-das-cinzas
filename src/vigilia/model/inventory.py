"""Posse de itens, requisitos de arma e carga equipada."""

from dataclasses import dataclass, field
from enum import StrEnum

from vigilia.core.timing import ROLL_STEPS_FAST, ROLL_STEPS_MID, ROLL_STEPS_HEAVY
from vigilia.model.items import WEAPONS, ITEM_WEIGHTS, PLAYER_WEAPON_IDS, Weapon
from vigilia.model.progression import Progression
from vigilia.model.stats import StatsBlock
from vigilia.model.spells import SPELLS


class RollTier(StrEnum):
    FAST = "fast"
    MID = "mid"
    HEAVY = "heavy"

    @property
    def steps(self) -> int:
        return {RollTier.FAST: ROLL_STEPS_FAST, RollTier.MID: ROLL_STEPS_MID,
                RollTier.HEAVY: ROLL_STEPS_HEAVY}[self]

    @property
    def speed(self) -> float:
        return {RollTier.FAST: 8.4, RollTier.MID: 7.5, RollTier.HEAVY: 5.3}[self]


def roll_tier(weight: float, capacity: float) -> RollTier:
    ratio = weight / capacity
    if ratio < .30:
        return RollTier.FAST
    return RollTier.MID if ratio < .70 else RollTier.HEAVY


@dataclass(slots=True)
class Inventory:
    items: dict[str, int] = field(default_factory=lambda: {
        "longsword": 1, "axe": 1, "armor": 1, "shield": 1, "shard": 3,
    })
    upgrades: dict[str, int] = field(default_factory=lambda: {"longsword": 0, "axe": 0})
    equipped_weapon: str = "longsword"
    equipped_gear: tuple[str, ...] = ("armor", "shield")

    @property
    def spells(self) -> tuple[str, ...]:
        return tuple(key for key in SPELLS if self.items.get(key, 0) > 0)

    def equip(self, weapon_id: str, stats: StatsBlock) -> Weapon:
        if (weapon_id not in PLAYER_WEAPON_IDS or not self.items.get(weapon_id, 0)
                or weapon_id not in self.upgrades):
            raise ValueError("Arma ausente do inventário.")
        spec = WEAPONS[weapon_id]
        if not stats.meets(spec.requirements):
            raise ValueError("Atributos insuficientes para equipar a arma.")
        weapon = spec.instantiate(self.upgrades[weapon_id])
        self.equipped_weapon = weapon_id
        return weapon

    @property
    def weapon(self) -> Weapon:
        return WEAPONS[self.equipped_weapon].instantiate(self.upgrades[self.equipped_weapon])

    @property
    def equip_weight(self) -> float:
        return WEAPONS[self.equipped_weapon].weight + sum(ITEM_WEIGHTS[key] for key in self.equipped_gear)

    @property
    def total_weight(self) -> float:
        return sum((WEAPONS[key].weight if key in WEAPONS else ITEM_WEIGHTS[key]) * count
                   for key, count in self.items.items())

    def mobility(self, stats: StatsBlock) -> RollTier:
        return roll_tier(self.equip_weight, stats.max_equip_load)

    def upgrade(self, progression: Progression) -> Weapon:
        """Valida todos os custos antes de consumir almas e materiais."""
        key = self.equipped_weapon
        level = self.upgrades[key]
        if level + 1 not in WEAPONS[key].upgrade_levels:
            raise ValueError("Arma já está na melhoria máxima.")
        shards, souls = level + 1, 80 * (level + 1) ** 2
        if self.items.get("shard", 0) < shards or progression.souls < souls:
            raise ValueError(f"A melhoria precisa de {shards} fragmentos e {souls} almas.")
        self.items["shard"] -= shards
        progression.souls -= souls
        self.upgrades[key] += 1
        return self.weapon
