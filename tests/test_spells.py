"""Conjuração usa o mesmo passo de combate, contatos e interrupções dos golpes."""

from types import SimpleNamespace
import pytest
from combat_fakes import ContactFake, PhysicsFake
from vigilia.combat.attack import Attack
from vigilia.combat.events import DamageDealt, HealingApplied, ShotFired
from vigilia.combat.fighter import Fighter
from vigilia.combat.orchestrator import CombatSystem
from vigilia.core.events import EventBus
from vigilia.core.mathx import Transform, Vec3
from vigilia.core.types import Action, HeldState, InputEdge
from vigilia.entities.ecs import World
from vigilia.model.characters import CHARACTER_CLASSES, create_character, starting_inventory
from vigilia.model.items import PRACTICE_SPEC, TRAINING_STATS
from vigilia.model.spells import SPELLS
from vigilia.player.state_machine import CombatController


def caster(identity):
    _, stats, weapon = create_character("Vesper", identity, {"vigor": 10})
    inventory = starting_inventory(identity)
    fighter = Fighter(0, inventory.equip(weapon, stats), stats)
    controller = CombatController(fighter, Transform(Vec3(0, 0, 1)), inventory)
    return fighter, controller


def cast(controller):
    controller.update(HeldState(), InputEdge(Action.CAST, True), Vec3(0, 1), dodging=False, critical=None)


def test_arcane_bolt_starts_only_after_owning_spell_and_spends_stamina():
    fighter, controller = caster("mage")
    initial = fighter.stamina
    cast(controller)
    assert fighter.attack.definition == SPELLS["ember_shard"].attack
    assert fighter.stamina == initial - 26
    previous = fighter.attack
    cast(controller)
    assert fighter.attack is previous and fighter.stamina == initial - 26
    fighter.attack = None
    controller.inventory.items["ember_shard"] = 0
    cast(controller)
    assert fighter.attack is None


def test_missing_stamina_catalyst_or_attributes_prevents_cast():
    fighter, controller = caster("mage")
    fighter.stamina = 25
    cast(controller)
    assert fighter.attack is None
    fighter.stamina = fighter.stats.max_stamina
    from dataclasses import replace
    fighter.stats = replace(fighter.stats, intelligence=1)
    cast(controller)
    assert fighter.attack is None


def test_magic_ray_damage_obeys_walls_and_can_only_hit_once():
    fighter, controller = caster("mage")
    cast(controller)
    world, contacts, physics, bus = World(), ContactFake(), PhysicsFake(), EventBus()
    source = world.spawn(controller.transform, fighter)
    defender = Fighter(1, PRACTICE_SPEC.instantiate(), TRAINING_STATS)
    target = world.spawn(Transform(Vec3(0, 4, 1)), defender)
    contacts.sync({(target.id, "torso"): (Vec3(0, 4, 1.25), .35)})
    events, shots = [], []
    bus.subscribe(DamageDealt, events.append)
    bus.subscribe(ShotFired, shots.append)
    combat = CombatSystem(contacts, physics, bus)
    hp = defender.hp
    combat.resolve(world)
    assert defender.hp == hp  # preparo não causa dano
    fighter.attack.age = 22
    combat.resolve(world)
    combat.resolve(world)
    assert defender.hp < hp and len(events) == len(shots) == 1
    assert events[0].damage_type == shots[0].damage_type == "magic"
    fighter.attack = Attack(SPELLS["ember_shard"].attack, age=22)
    physics.wall = SimpleNamespace(distance=1, point=Vec3(0, 1, 1.25))
    combat.resolve(world)
    assert len(events) == 1 and len(shots) == 2


def test_heal_applies_once_at_active_frame_and_is_limited_by_max_hp():
    fighter, controller = caster("cleric")
    fighter.hp -= 30
    cast(controller)
    world, bus = World(), EventBus()
    entity = world.spawn(controller.transform, fighter)
    healed = []
    bus.subscribe(HealingApplied, healed.append)
    combat = CombatSystem(ContactFake(), PhysicsFake(), bus)
    hp = fighter.hp
    combat.resolve(world)
    assert fighter.hp == hp
    fighter.attack.age = 30
    combat.resolve(world)
    combat.resolve(world)
    assert fighter.hp == fighter.max_hp and healed == [HealingApplied(entity.id, 30)]


def test_full_hp_does_not_spend_and_stagger_interrupts_healing():
    fighter, controller = caster("cleric")
    stamina = fighter.stamina
    cast(controller)
    assert fighter.attack is None and fighter.stamina == stamina
    fighter.hp -= 90
    cast(controller)
    fighter.interrupt(15)
    world = World()
    world.spawn(controller.transform, fighter)
    hp = fighter.hp
    CombatSystem(ContactFake(), PhysicsFake(), EventBus()).resolve(world)
    assert fighter.hp == hp


def test_charged_mace_keeps_its_holy_damage_channel():
    fighter, controller = caster("cleric")
    controller.update(HeldState(), InputEdge(Action.HEAVY, True), Vec3(0, 1), dodging=False, critical=None)
    controller.update(HeldState(), InputEdge(Action.HEAVY, False), Vec3(0, 1), dodging=False, critical=None)
    assert fighter.attack.definition.packet.holy > controller.moveset.heavy.packet.holy > 0
    assert fighter.attack.definition.packet.physical_strike > controller.moveset.heavy.packet.physical_strike


@pytest.mark.parametrize("identity", tuple(CHARACTER_CLASSES))
def test_weapon_swap_is_safe_with_a_single_starting_weapon(identity):
    fighter, controller = caster(identity)
    previous = fighter.weapon
    controller.update(HeldState(), InputEdge(Action.SWAP_WEAPON, True), Vec3(0, 1), dodging=False, critical=None)
    assert fighter.weapon == previous
