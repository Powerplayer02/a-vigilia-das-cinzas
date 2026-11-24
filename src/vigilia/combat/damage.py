"""Cálculo puro de dano, resistências e guarda."""

from dataclasses import dataclass, fields

from vigilia.model.items import Weapon, WeaponSpec
from vigilia.model.stats import ResistBlock, StatsBlock
from vigilia.model.attacks import DamagePacket


@dataclass(frozen=True, slots=True)
class DamageResult:
    hp: float
    poise: float
    guard_cost: float


def resolve_damage(packet: DamagePacket, attacker_stats: StatsBlock, weapon: Weapon | WeaponSpec,
                   defender_stats: StatsBlock, defender_resist: ResistBlock, *,
                   is_backstab: bool = False, is_riposte: bool = False,
                   is_blocked: bool = False) -> DamageResult:
    """Escala cada tipo de dano, aplica resistência e calcula o custo de guarda."""
    if isinstance(weapon, WeaponSpec):
        weapon = weapon.instantiate()
    physical = attacker_stats.strength * weapon.strength + attacker_stats.dexterity * weapon.dexterity
    scaling = {
        "fire": attacker_stats.intelligence * weapon.intelligence,
        "magic": attacker_stats.intelligence * weapon.intelligence,
        "holy": attacker_stats.faith * weapon.faith,
    }
    critical = 2.35 if is_riposte else 1.85 if is_backstab else 1.0
    raw = 0.0
    for channel in fields(ResistBlock):
        base = max(0.0, getattr(packet, channel.name))
        factor = 1 + .025 * scaling.get(channel.name, physical) + .09 * weapon.upgrade
        defense = max(-50.0, getattr(defender_resist, channel.name) + .6 * defender_stats.endurance)
        raw += base * factor * 100 / (100 + defense)
    raw *= critical
    blocked = is_blocked and critical == 1.0
    return DamageResult(raw * (.22 if blocked else 1),
                        packet.poise * (.22 if blocked else critical),
                        packet.poise * .65 + raw * .25 if blocked else 0)
