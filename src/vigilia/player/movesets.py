"""Seleção de movimentos a partir das definições do domínio."""

from dataclasses import dataclass

from vigilia.model.attacks import AttackDefinition, AttackKind
from vigilia.model.items import AXE_SPEC, LONGSWORD_SPEC, Weapon, WeaponSpec, WEAPONS


@dataclass(frozen=True, slots=True)
class Moveset:
    weapon: Weapon
    light: tuple[AttackDefinition, ...]
    heavy: AttackDefinition
    running: AttackDefinition
    riposte: AttackDefinition
    backstab: AttackDefinition
    slide: AttackDefinition

    @classmethod
    def from_spec(cls, spec: WeaponSpec, upgrade: int = 0) -> "Moveset":
        """Monta as ações sem definir dano no controlador."""
        lights = tuple(attack for attack in spec.attacks if attack.kind in
                       (AttackKind.LIGHT_1, AttackKind.LIGHT_2, AttackKind.LIGHT_3))
        return cls(spec.instantiate(upgrade), lights, spec.attack(AttackKind.HEAVY),
                   spec.attack(AttackKind.RUNNING), spec.attack(AttackKind.RIPOSTE),
                   spec.attack(AttackKind.BACKSTAB), spec.attack(AttackKind.SLIDING))


LONGSWORD = Moveset.from_spec(LONGSWORD_SPEC)
AXE = Moveset.from_spec(AXE_SPEC)


def for_weapon(weapon: Weapon) -> Moveset:
    return Moveset.from_spec(WEAPONS[weapon.spec_id], weapon.upgrade)
