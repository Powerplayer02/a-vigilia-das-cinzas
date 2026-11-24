"""Buffers de combo e carga, gasto de estamina e recuperação."""

from vigilia.combat.attack import AttackKind
from vigilia.combat.fighter import Fighter
from vigilia.combat.status import StatusEffect, StatusStack
from vigilia.core.mathx import Transform, Vec3
from vigilia.core.types import Action, HeldState, InputEdge
from vigilia.player.movesets import AXE, LONGSWORD
from vigilia.player.state_machine import CombatController


def test_combo_buffer_executes_next_hit_once_at_cancel_window() -> None:
    fighter = Fighter(0, LONGSWORD.weapon)
    controller = CombatController(fighter, Transform())
    def command(edge=None):
        controller.update(HeldState(), edge, Vec3(0, 1), dodging=False, critical=None)
    command(InputEdge(Action.LIGHT, True))
    assert fighter.attack.definition.kind == AttackKind.LIGHT_1
    fighter.attack.age = 12
    command(InputEdge(Action.LIGHT, True))
    assert fighter.attack.definition.kind == AttackKind.LIGHT_1
    fighter.attack.age = 22
    command()
    assert fighter.attack.definition.kind == AttackKind.LIGHT_2
    assert fighter.stamina == fighter.stats.max_stamina - 31
    command()
    assert fighter.attack.definition.kind == AttackKind.LIGHT_2
    assert fighter.attack.age == 0


def test_releasing_heavy_starts_one_scaled_attack_and_charges_once() -> None:
    fighter = Fighter(0, LONGSWORD.weapon)
    controller = CombatController(fighter, Transform())
    controller.update(HeldState(), InputEdge(Action.HEAVY, True), Vec3(0, 1),
                      dodging=False, critical=None)
    for _ in range(20):
        controller.update(HeldState(), None, Vec3(0, 1), dodging=False, critical=None)
    assert fighter.attack is None
    controller.update(HeldState(), InputEdge(Action.HEAVY, False), Vec3(0, 1),
                      dodging=False, critical=None)
    assert fighter.attack.definition.kind == AttackKind.HEAVY
    assert fighter.attack.definition.packet.physical_slash > LONGSWORD.heavy.packet.physical_slash
    assert fighter.stamina == fighter.stats.max_stamina - 30
    controller.update(HeldState(), None, Vec3(0, 1), dodging=False, critical=None)
    assert fighter.stamina == fighter.stats.max_stamina - 30


def test_empty_stamina_rejects_attack_and_stagger_interrupts_it() -> None:
    fighter = Fighter(0, AXE.weapon)
    fighter.stamina = 0
    assert not fighter.start(AXE.heavy)
    assert fighter.attack is None
    fighter.stamina = 100
    assert fighter.start(AXE.heavy)
    fighter.interrupt(24)
    assert fighter.attack is None
    assert fighter.stagger_steps == 24


def test_status_ticks_end_and_curse_persists_until_restoration() -> None:
    stack = StatusStack()
    assert stack.apply(StatusEffect.BLEED, 100, 200) == 32
    assert stack.apply(StatusEffect.POISON, 100, 200) == 0
    total = sum(stack.tick() for _ in range(720))
    assert abs(total - 60) < 1e-6
    assert StatusEffect.POISON not in stack.active
    stack.apply(StatusEffect.FROST, 100, 200)
    stack.apply(StatusEffect.CURSE, 100, 200)
    for _ in range(421):
        stack.tick()
    assert StatusEffect.FROST not in stack.active
    assert stack.active[StatusEffect.CURSE] == -1
    fighter = Fighter(0, LONGSWORD.weapon)
    fighter.status = stack
    assert fighter.max_hp == fighter.stats.max_hp * .7
    fighter.restore()
    assert fighter.hp == fighter.max_hp == fighter.stats.max_hp
    assert not fighter.status.active
