"""Definições e instâncias de ataque em passos de simulação."""

from dataclasses import dataclass, field
from vigilia.model.attacks import AttackDefinition, AttackKind, HitboxKind
from vigilia.core.mathx import Vec3


@dataclass(slots=True)
class Attack:
    definition: AttackDefinition
    age: int = 0
    hit_targets: set[int] = field(default_factory=set)
    victim: int | None = None
    aim: Vec3 | None = None
    fired: bool = False

    @property
    def active(self) -> bool:
        return self.definition.windup <= self.age < self.definition.windup + self.definition.active
