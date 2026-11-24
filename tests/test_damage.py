"""Dano por tipo, atributos, críticos e guarda com valores conhecidos."""

import math

import pytest

from vigilia.combat.damage import DamagePacket, resolve_damage
from vigilia.combat.orchestrator import behind
from vigilia.core.mathx import Transform, Vec3
from vigilia.model.items import Weapon
from vigilia.model.items import LONGSWORD_SPEC
from vigilia.model.stats import StatsBlock, ResistBlock


def test_split_damage_uses_the_resistance_of_each_channel() -> None:
    result = resolve_damage(DamagePacket(physical_slash=100, fire=80, poise=20),
                            StatsBlock(endurance=0), Weapon("teste"),
                            StatsBlock(endurance=0), ResistBlock(physical_slash=100))
    assert result.hp == 130
    assert result.poise == 20
    assert result.guard_cost == 0


def test_scaling_and_critical_multipliers_are_applied_once() -> None:
    args = (DamagePacket(physical_slash=40, poise=20), StatsBlock(strength=20),
            Weapon("teste", strength=1), StatsBlock(endurance=0), ResistBlock())
    assert resolve_damage(*args).hp == 60
    assert resolve_damage(*args, is_backstab=True).hp == pytest.approx(111)
    assert resolve_damage(*args, is_riposte=True, is_backstab=True).hp == 141
    blocked = resolve_damage(*args, is_blocked=True)
    assert blocked.hp == pytest.approx(13.2)
    assert blocked.guard_cost == 28
    assert resolve_damage(*args, is_riposte=True, is_blocked=True).hp == 141


def test_backstab_requires_a_position_in_the_rear_cone() -> None:
    defender = Transform(Vec3(), 0)
    assert behind(Transform(Vec3(0, -1)), defender)
    assert not behind(Transform(Vec3(1, 0)), defender)
    assert not behind(Transform(Vec3(0, 1)), defender)
    assert behind(Transform(Vec3(0, 1)), Transform(Vec3(), math.pi))


def test_catalog_weapon_preserves_the_frozen_damage_formula() -> None:
    stats = StatsBlock()
    packet = LONGSWORD_SPEC.base
    from_spec = resolve_damage(packet, stats, LONGSWORD_SPEC, stats, ResistBlock())
    from_instance = resolve_damage(packet, stats, LONGSWORD_SPEC.instantiate(), stats, ResistBlock())
    assert from_spec == from_instance
    assert from_spec.hp == pytest.approx(25 * (1 + .025 * 11.5) * 100 / 106)
