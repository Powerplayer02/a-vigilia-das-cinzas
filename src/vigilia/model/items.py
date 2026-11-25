"""Catálogo de armas e seus dados numéricos, independente dos controladores."""

from dataclasses import dataclass, replace
from enum import StrEnum

from vigilia.model.attacks import AttackDefinition, AttackKind as Kind, DamagePacket, StatusEffect
from vigilia.model.stats import StatsBlock


class ScalingGrade(StrEnum):
    NONE = "-"
    S = "S"
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"

    @property
    def coefficient(self) -> float:
        return {"-": 0, "S": 1.05, "A": .85, "B": .65, "C": .50, "D": .30, "E": .15}[self.value]


@dataclass(frozen=True, slots=True)
class ScalingGrades:
    strength: ScalingGrade = ScalingGrade.NONE
    dexterity: ScalingGrade = ScalingGrade.NONE
    intelligence: ScalingGrade = ScalingGrade.NONE
    faith: ScalingGrade = ScalingGrade.NONE


@dataclass(frozen=True, slots=True)
class Weapon:
    """Arma equipada. spec_id identifica a definição persistente do catálogo."""

    name: str
    strength: float = 0
    dexterity: float = 0
    intelligence: float = 0
    faith: float = 0
    upgrade: int = 0
    spec_id: str = ""


@dataclass(frozen=True, slots=True)
class WeaponSpec:
    id: str
    display_name: str
    base: DamagePacket
    scaling: ScalingGrades
    requirements: StatsBlock
    upgrade_levels: tuple[int, ...]
    moveset_id: str
    weight: float
    attacks: tuple[AttackDefinition, ...]

    def instantiate(self, upgrade: int = 0) -> Weapon:
        """Cria uma arma equipada a partir de sua definição persistente."""
        if upgrade not in self.upgrade_levels:
            raise ValueError("Nível de melhoria inválido.")
        scaling = self.scaling
        return Weapon(self.display_name, scaling.strength.coefficient, scaling.dexterity.coefficient,
                      scaling.intelligence.coefficient, scaling.faith.coefficient, upgrade, self.id)

    def attack(self, kind: Kind) -> AttackDefinition:
        if kind in (Kind.SLIDING, Kind.DASH_ATTACK, Kind.WALKING_ATTACK):
            from vigilia.core.timing import (SLIDE_ATTACK_WINDUP, SLIDE_ATTACK_ACTIVE,
                SLIDE_ATTACK_RECOVERY, DASH_ATTACK_WINDUP, DASH_ATTACK_ACTIVE, DASH_ATTACK_RECOVERY)
            light = self.attack(Kind.LIGHT_1)
            power = {Kind.SLIDING: 1.6, Kind.DASH_ATTACK: 2., Kind.WALKING_ATTACK: 1.1}[kind]
            packet = DamagePacket(**{name: getattr(light.packet, name) * power for name in
                ('physical_slash', 'physical_strike', 'physical_pierce', 'fire', 'magic', 'holy', 'poise')})
            if kind == Kind.WALKING_ATTACK:
                return replace(light, kind=kind, packet=packet, cancel_from=None)
            windup, active, recovery, stamina = ((SLIDE_ATTACK_WINDUP, SLIDE_ATTACK_ACTIVE,
                SLIDE_ATTACK_RECOVERY, 18) if kind == Kind.SLIDING else
                (DASH_ATTACK_WINDUP, DASH_ATTACK_ACTIVE, DASH_ATTACK_RECOVERY, 24))
            return replace(light, kind=kind, packet=packet, windup=windup, active=active,
                recovery=recovery, stamina=stamina, cancel_from=None)
        return next(attack for attack in self.attacks if attack.kind == kind)


def _strike(kind: Kind, timing: tuple[int, int, int], cost: int, damage: int,
            poise: int, reach: float, arc: float, *, axe: bool = False,
            combo: int | None = None) -> AttackDefinition:
    packet = (DamagePacket(physical_strike=damage, poise=poise) if axe
              else DamagePacket(physical_slash=damage, poise=poise))
    return AttackDefinition(kind, *timing, cost, packet, reach, arc, cancel_from=combo)


LONGSWORD_SPEC = WeaponSpec(
    "longsword", "Espada longa", DamagePacket(physical_slash=25, poise=16),
    ScalingGrades(ScalingGrade.B, ScalingGrade.C), StatsBlock(0, 0, 8, 8, 0, 0, 0),
    (0, 1, 2, 3), "longsword", 4.8,
    (_strike(Kind.LIGHT_1, (11, 7, 17), 15, 25, 16, 1.57, 2.1, combo=22),
     _strike(Kind.LIGHT_2, (9, 7, 18), 16, 28, 18, 1.59, -2.4, combo=21),
     _strike(Kind.LIGHT_3, (14, 8, 24), 20, 37, 25, 1.63, 2.5),
     _strike(Kind.HEAVY, (17, 9, 25), 30, 45, 39, 1.72, -1.7),
     _strike(Kind.RUNNING, (10, 8, 20), 24, 35, 25, 1.77, 1.75),
     _strike(Kind.RIPOSTE, (12, 5, 25), 18, 42, 35, 1.75, .30),
     _strike(Kind.BACKSTAB, (11, 5, 24), 17, 41, 33, 1.60, -.30)),
)
AXE_SPEC = WeaponSpec(
    "axe", "Machado", DamagePacket(physical_strike=36, poise=27),
    ScalingGrades(ScalingGrade.S, ScalingGrade.E), StatsBlock(0, 0, 10, 5, 0, 0, 0),
    (0, 1, 2, 3), "axe", 6.8,
    (_strike(Kind.LIGHT_1, (15, 8, 22), 21, 36, 27, 1.40, 2.8, axe=True, combo=30),
     _strike(Kind.LIGHT_2, (16, 9, 26), 24, 43, 33, 1.52, -2.6, axe=True),
     AttackDefinition(Kind.HEAVY, 21, 10, 29, 34, DamagePacket(physical_strike=59, poise=50),
                      1.56, 2.1, status=(StatusEffect.BLEED, 57)),
     _strike(Kind.RUNNING, (15, 8, 24), 28, 43, 33, 1.60, -2.6, axe=True),
     _strike(Kind.RIPOSTE, (15, 5, 27), 21, 49, 41, 1.56, .35, axe=True),
     _strike(Kind.BACKSTAB, (15, 5, 27), 19, 49, 39, 1.50, -.35, axe=True)),
)
PRACTICE_SPEC = WeaponSpec(
    "practice_staff", "Bastão de treino", DamagePacket(physical_strike=19, poise=22),
    ScalingGrades(), StatsBlock(0, 0, 0, 0, 0, 0, 0), (0,), "practice_staff", 2,
    (AttackDefinition(Kind.PRACTICE, 42, 9, 38, 0,
                      DamagePacket(physical_strike=19, poise=22), 1.87, 1.2),),
)
CINDER_SPEC = WeaponSpec(
    "cinder_blade", "Lâmina de sal", DamagePacket(physical_slash=29, poise=36),
    ScalingGrades(ScalingGrade.D), StatsBlock(0, 0, 0, 0, 0, 0, 0), (0,), "cinzeiro", 5,
    (AttackDefinition(Kind.LIGHT_1, 34, 8, 30, 0,
                      DamagePacket(physical_slash=29, poise=36), 1.75, 1.9),),
)
RANCOR_SPEC = WeaponSpec(
    "rancor_knives", "Facas do lodo", DamagePacket(physical_slash=14, poise=12),
    ScalingGrades(dexterity=ScalingGrade.E), StatsBlock(0, 0, 0, 0, 0, 0, 0),
    (0,), "rancor", 2,
    (AttackDefinition(Kind.LIGHT_1, 10, 6, 8, 0,
                      DamagePacket(physical_slash=14, poise=12), 1.38, 2.4),
     AttackDefinition(Kind.LIGHT_2, 8, 7, 24, 0,
                      DamagePacket(physical_slash=19, poise=18), 1.45, -2.5)),
)
CROSSBOW_SPEC = WeaponSpec(
    "vesper_crossbow", "Besta de Vesper", DamagePacket(physical_pierce=24, poise=16),
    ScalingGrades(), StatsBlock(0, 0, 0, 0, 0, 0, 0), (0,), "bestario", 4,
    (AttackDefinition(Kind.LIGHT_1, 38, 1, 72, 0,
                      DamagePacket(physical_pierce=24, poise=16), 14, 0, ranged=True),),
)
KATANA_SPEC = WeaponSpec(
    "katana", "Katana do exílio", DamagePacket(physical_slash=21, poise=12),
    ScalingGrades(ScalingGrade.E, ScalingGrade.A), StatsBlock(0, 0, 8, 12, 0, 0, 0),
    (0, 1, 2, 3), "katana", 3.2,
    (_strike(Kind.LIGHT_1, (8, 6, 15), 13, 21, 12, 1.65, 1.9, combo=19),
     _strike(Kind.LIGHT_2, (8, 6, 16), 14, 24, 14, 1.68, -2.1, combo=19),
     _strike(Kind.LIGHT_3, (11, 7, 22), 18, 31, 20, 1.75, 2.3),
     _strike(Kind.HEAVY, (18, 7, 24), 27, 40, 29, 1.85, -.9),
     _strike(Kind.RUNNING, (9, 6, 19), 21, 30, 20, 1.86, 1.8),
     _strike(Kind.RIPOSTE, (11, 5, 24), 17, 42, 32, 1.7, .3),
     _strike(Kind.BACKSTAB, (10, 5, 23), 16, 44, 31, 1.65, -.3)),
)
STAFF_SPEC = WeaponSpec(
    "staff", "Cajado da brasa fria", DamagePacket(physical_strike=16, poise=13),
    ScalingGrades(strength=ScalingGrade.E, intelligence=ScalingGrade.A),
    StatsBlock(0, 0, 0, 0, 12, 0, 0), (0, 1, 2, 3), "staff", 2.4,
    (_strike(Kind.LIGHT_1, (16, 7, 23), 14, 16, 13, 1.75, 1.8, axe=True, combo=29),
     _strike(Kind.LIGHT_2, (18, 7, 27), 16, 20, 17, 1.8, -2, axe=True),
     _strike(Kind.HEAVY, (23, 8, 30), 25, 30, 26, 1.9, -1.6, axe=True),
     _strike(Kind.RUNNING, (14, 7, 24), 21, 24, 20, 1.9, 2, axe=True),
     _strike(Kind.RIPOSTE, (16, 5, 27), 18, 32, 29, 1.8, .3, axe=True),
     _strike(Kind.BACKSTAB, (16, 5, 27), 17, 32, 28, 1.7, -.3, axe=True)),
)
MACE_SPEC = WeaponSpec(
    "mace", "Maça da Vigília", DamagePacket(physical_strike=24, holy=6, poise=25),
    ScalingGrades(strength=ScalingGrade.C, faith=ScalingGrade.B),
    StatsBlock(0, 0, 10, 0, 0, 10, 0), (0, 1, 2, 3), "mace", 4.5,
    tuple(replace(attack, stamina=max(12, attack.stamina - 3), reach=attack.reach + .05, status=None,
        packet=DamagePacket(physical_strike=attack.packet.physical_strike * .65,
                            holy=attack.packet.physical_strike * .18, poise=attack.packet.poise))
        for attack in AXE_SPEC.attacks),
)
WEAPONS = {spec.id: spec for spec in (
    LONGSWORD_SPEC, AXE_SPEC, KATANA_SPEC, STAFF_SPEC, MACE_SPEC,
    PRACTICE_SPEC, CINDER_SPEC, RANCOR_SPEC, CROSSBOW_SPEC,
)}
PLAYER_WEAPON_IDS = ("longsword", "axe", "katana", "staff", "mace")
TRAINING_STATS = StatsBlock(vigor=40, endurance=12)
DUMMY_SOULS = 80
GEAR_IDS = ("armor", "shield", "leather_armor", "robe")
ITEM_WEIGHTS = {"armor": 16.0, "shield": 5.0, "shard": .1, "leather_armor": 7., "robe": 3.,
                "ember_shard": 0., "mending_light": 0., "tide_signet": 0., "ember_heart": 0.}
