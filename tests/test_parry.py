"""Fronteiras exatas de parry e i-frames com contatos simulados."""

import math

import pytest

from combat_fakes import ContactFake, PhysicsFake
from vigilia.combat.attack import Attack, AttackDefinition, AttackKind
from vigilia.combat.damage import DamagePacket
from vigilia.combat.events import ParrySucceeded, DamageDealt
from vigilia.combat.fighter import Fighter
from vigilia.combat.orchestrator import CombatSystem
from vigilia.combat.parry import parry_outcome, ParryOutcome
from vigilia.core.events import EventBus
from vigilia.core.mathx import Transform, Vec3
from vigilia.core.types import Action, HeldState, InputEdge
from vigilia.entities.ecs import World
from vigilia.player.controller import PlayerController
from vigilia.model.items import Weapon


@pytest.mark.parametrize(("age", "outcome"), [
    (-1, ParryOutcome.MISS), (0, ParryOutcome.SUCCESS), (11, ParryOutcome.SUCCESS),
    (12, ParryOutcome.LATE_BLOCK), (13, ParryOutcome.MISS),
])
def test_parry_age_boundaries(age, outcome) -> None:
    assert parry_outcome(age) == outcome


@pytest.mark.parametrize(("age", "parried", "blocked"), [(11, True, False), (12, False, True), (13, False, False)])
def test_shield_weapon_contact_parries_then_blocks_then_takes_full_damage(age, parried, blocked) -> None:
    world, bus, contacts = World(), EventBus(), ContactFake()
    attacker, defender = Fighter(1, Weapon("bastão")), Fighter(0, Weapon("espada"))
    attack = AttackDefinition(AttackKind.PRACTICE, 0, 4, 5, 0,
                              DamagePacket(physical_strike=20, poise=10), 1.6, 1)
    attacker.attack = Attack(attack)
    defender.parry_step = age
    a = world.spawn(Transform(Vec3(0, 1), math.pi), attacker)
    d = world.spawn(Transform(Vec3()), defender)
    contacts.sync({(a.id, "blade_mid"): (Vec3(0, .4), .25),
                   (d.id, "shield"): (Vec3(0, .4), .3),
                   (d.id, "torso"): (Vec3(0, .1), .3)})
    successes, hits = [], []
    bus.subscribe(ParrySucceeded, successes.append)
    bus.subscribe(DamageDealt, hits.append)
    CombatSystem(contacts, PhysicsFake(), bus).resolve(world)
    assert bool(successes) == parried
    if parried:
        assert defender.hp == defender.max_hp
        assert attacker.riposte_steps == 90
        assert attacker.attack is None
    else:
        assert hits[0].blocked == blocked
        assert hits[0].amount == pytest.approx((20 * 100 / 106) * (.22 if blocked else 1))


def test_roll_has_exactly_twelve_invulnerable_steps() -> None:
    fighter = Fighter(0, Weapon("espada"))
    player = PlayerController(PhysicsFake(), Transform())
    held = HeldState(frozenset(), 0, 1)
    invulnerable = []
    for step in range(33):
        edge = InputEdge(Action.ROLL, True) if step == 0 else None
        player.update(held, edge, Vec3(0, 1), Vec3(1, 0), locked=False, fighter=fighter)
        if fighter.invulnerable:
            invulnerable.append(step)
    assert invulnerable == list(range(2, 14))
    assert fighter.stamina == fighter.stats.max_stamina - 24


def test_insufficient_stamina_breaks_guard_and_applies_full_damage() -> None:
    world, bus, contacts = World(), EventBus(), ContactFake()
    attacker, defender = Fighter(1, Weapon("bastão")), Fighter(0, Weapon("espada"))
    attacker.attack = Attack(AttackDefinition(
        AttackKind.PRACTICE, 0, 4, 5, 0, DamagePacket(physical_strike=20, poise=10), 1.6, 1,
    ))
    defender.blocking, defender.stamina = True, 1
    a = world.spawn(Transform(Vec3(0, 1), math.pi), attacker)
    d = world.spawn(Transform(), defender)
    contacts.sync({(a.id, "blade_mid"): (Vec3(0, .4), .25),
                   (d.id, "shield"): (Vec3(0, .4), .3)})
    CombatSystem(contacts, PhysicsFake(), bus).resolve(world)
    assert defender.stamina == 0
    assert defender.stagger_steps == 42
    assert defender.hp == pytest.approx(defender.max_hp - 20 * 100 / 106)
    assert not defender.blocking
