"""Perfis dos adversários de Vesper."""

from dataclasses import dataclass, field

from vigilia.model.attacks import AttackDefinition
from vigilia.model.items import CINDER_SPEC, RANCOR_SPEC, CROSSBOW_SPEC, WeaponSpec
from vigilia.model.stats import StatsBlock
from vigilia.model.stats import ResistBlock
from vigilia.model.attacks import AttackKind, DamagePacket, StatusEffect
from vigilia.model.items import ScalingGrades, WEAPONS


@dataclass(frozen=True, slots=True)
class EnemyProfile:
    id: str
    name: str
    weapon: WeaponSpec
    stats: StatsBlock
    speed: float
    detection_radius: float
    attack_range: float
    min_range: float
    souls: int
    tint: tuple[float, float, float, float]
    resist: ResistBlock = field(default_factory=ResistBlock)

    @property
    def attacks(self) -> tuple[AttackDefinition, ...]:
        return self.weapon.attacks

    @property
    def ranged(self) -> bool:
        return self.attacks[0].ranged


CINZEIRO = EnemyProfile(
    "cinzeiro", "Cinzeiro", CINDER_SPEC, StatsBlock(vigor=14, endurance=25, strength=14),
    1.8, 13, 1.85, 0, 100, (.28, .26, .22, 1),
)
RANCOR = EnemyProfile(
    "rancor", "Rancor", RANCOR_SPEC, StatsBlock(vigor=5, endurance=0, dexterity=16),
    3.4, 12, 1.55, 0, 75, (.48, .12, .13, 1),
)
BESTARIO = EnemyProfile(
    "bestario", "Bestário", CROSSBOW_SPEC, StatsBlock(vigor=7, endurance=10),
    2.3, 16, 12, 4.5, 90, (.17, .30, .38, 1),
)
ENEMIES = {profile.id: profile for profile in (CINZEIRO, RANCOR, BESTARIO)}


def _weapon(identity, attacks):
    weapon = WeaponSpec(identity, identity, attacks[0].packet, ScalingGrades(), StatsBlock(0, 0, 0, 0, 0, 0, 0),
        (0,), identity, 3., tuple(attacks))
    WEAPONS[identity] = weapon
    return weapon


SALT_GUARD = EnemyProfile("salt_guard", "Vigia de sal", _weapon("salt_spear", (
    AttackDefinition(AttackKind.LIGHT_1, 33, 8, 24, 0, DamagePacket(physical_pierce=24, poise=24), 2.4, .45),
    AttackDefinition(AttackKind.LIGHT_2, 18, 8, 48, 0, DamagePacket(physical_pierce=29, poise=32), 2.5, .5))),
    StatsBlock(vigor=25, endurance=24, strength=12), 2., 14., 2.4, 0., 145, (.65, .70, .61, 1),
    ResistBlock(physical_slash=12, physical_strike=2, physical_pierce=8, magic=10))
OSSUARY_ACOLYTE = EnemyProfile("ossuary_acolyte", "Acólito do ossário", _weapon("ossuary_lantern", (
    AttackDefinition(AttackKind.ARCANE_BOLT, 54, 1, 75, 0, DamagePacket(magic=30, poise=18), 15., 0.,
        parryable=False, ranged=True),)), StatsBlock(vigor=14, endurance=10, intelligence=18),
    2.2, 17., 14., 5., 155, (.23, .42, .58, 1), ResistBlock(magic=24, holy=-15))
BOG_GHOUL = EnemyProfile("bog_ghoul", "Carniçal do lodo", _weapon("bog_claws", (
    AttackDefinition(AttackKind.RUNNING, 24, 9, 36, 0, DamagePacket(physical_slash=24, poise=20), 2., 1.2,
        status=(StatusEffect.POISON, 32)),
    AttackDefinition(AttackKind.LIGHT_1, 20, 8, 48, 0, DamagePacket(physical_pierce=27, poise=16), 1.7, 1.1,
        status=(StatusEffect.POISON, 40)))), StatsBlock(vigor=19, endurance=8, dexterity=20),
    3.3, 13., 1.9, 0., 135, (.27, .36, .17, 1), ResistBlock(fire=-18, magic=8))
ENEMIES.update({profile.id: profile for profile in (SALT_GUARD, OSSUARY_ACOLYTE, BOG_GHOUL)})
