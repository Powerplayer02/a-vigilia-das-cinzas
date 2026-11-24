"""Magias iniciais usam estamina, preparação e recuperação do combate existente."""

from dataclasses import dataclass
from vigilia.model.attacks import AttackDefinition, AttackKind, DamagePacket
from vigilia.model.stats import StatsBlock


@dataclass(frozen=True, slots=True)
class SpellDefinition:
    id: str
    requirements: StatsBlock
    catalyst: str
    attack: AttackDefinition

    def can_cast(self, stats: StatsBlock, weapon_id: str) -> bool:
        return stats.meets(self.requirements) and weapon_id == self.catalyst


SPELLS = {spell.id: spell for spell in (
    SpellDefinition("ember_shard", StatsBlock(0, 0, 0, 0, 12, 0, 0), "staff",
        AttackDefinition(AttackKind.ARCANE_BOLT, 22, 1, 25, 26,
            DamagePacket(magic=36, poise=14), 15, 0, parryable=False, ranged=True)),
    SpellDefinition("mending_light", StatsBlock(0, 0, 0, 0, 0, 12, 0), "mace",
        AttackDefinition(AttackKind.MENDING_LIGHT, 30, 1, 32, 35,
            DamagePacket(), 1, 0, parryable=False, healing=40)),
)}
