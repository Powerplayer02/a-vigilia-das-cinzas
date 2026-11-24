"""Eventos imutáveis do combate."""

from dataclasses import dataclass

from vigilia.core.events import Event, SfxRequestedEvent
from vigilia.core.mathx import Vec3


@dataclass(frozen=True, slots=True)
class DamageDealt(Event):
    source: int
    target: int
    amount: float
    remaining_hp: float
    blocked: bool
    critical: str
    damage_type: str = "physical"
    attack_kind: str = ""


@dataclass(frozen=True, slots=True)
class ParrySucceeded(Event):
    defender: int
    attacker: int


@dataclass(frozen=True, slots=True)
class StaggerTriggered(Event):
    target: int
    guard_broken: bool


@dataclass(frozen=True, slots=True)
class EntityDied(Event):
    target: int


@dataclass(frozen=True, slots=True)
class ShotFired(Event):
    source: int
    origin: Vec3
    end: Vec3
    damage_type: str = "physical"


@dataclass(frozen=True, slots=True)
class HPChangedEvent(Event):
    entity_id: int
    old_hp: float
    new_hp: float
    max_hp: float
    source_kind: str


@dataclass(frozen=True, slots=True)
class HealingApplied(Event):
    target: int
    amount: float
