"""Dados de ataque compartilhados pelo catálogo e pelas regras de combate."""

from dataclasses import dataclass
from enum import StrEnum, auto


class StatusEffect(StrEnum):
    BLEED = auto()
    POISON = auto()
    FROST = auto()
    CURSE = auto()


class AttackKind(StrEnum):
    LIGHT_1 = auto()
    LIGHT_2 = auto()
    LIGHT_3 = auto()
    HEAVY = auto()
    RUNNING = auto()
    SLIDING = auto()
    RIPOSTE = auto()
    BACKSTAB = auto()
    PRACTICE = auto()
    SLOW_OVERHEAD = auto()
    WIDE_SWEEP = auto()
    BACKSTEP_PUNISH = auto()
    FORGE_GRAB = auto()
    FIRE_AOE_RING = auto()
    ARCANE_BOLT = auto()
    MENDING_LIGHT = auto()
    TIDE_STRIKE = auto()
    TIDE_SWEEP = auto()
    TIDE_BOLT = auto()
    TIDE_GRASP = auto()
    TIDE_NOVA = auto()


class HitboxKind(StrEnum):
    BONE_SPHERE = "bone_sphere"
    CENTER_SPHERE = "center_sphere"


@dataclass(frozen=True, slots=True)
class DamagePacket:
    physical_slash: float = 0
    physical_strike: float = 0
    physical_pierce: float = 0
    fire: float = 0
    magic: float = 0
    holy: float = 0
    poise: float = 0


@dataclass(frozen=True, slots=True)
class AttackDefinition:
    kind: AttackKind
    windup: int
    active: int
    recovery: int
    stamina: float
    packet: DamagePacket
    reach: float
    arc: float
    cancel_from: int | None = None
    parryable: bool = True
    status: tuple[StatusEffect, float] | None = None
    ranged: bool = False
    hitbox_kind: HitboxKind = HitboxKind.BONE_SPHERE
    sphere_radius_start: float = 0
    sphere_radius_end: float = 0
    blockable: bool = True
    block_damage_fraction: float = .22
    knockdown_steps: int = 0
    healing: float = 0

    @property
    def duration(self) -> int:
        return self.windup + self.active + self.recovery
