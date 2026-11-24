"""Pose, contatos e prevenção de danos repetidos em um ataque."""

import math

from combat_fakes import ContactFake, PhysicsFake
from vigilia.combat.attack import Attack
from vigilia.combat.events import DamageDealt
from vigilia.combat.fighter import Fighter
from vigilia.combat.hitbox import evaluate_pose
from vigilia.combat.orchestrator import CombatSystem
from vigilia.core.events import EventBus
from vigilia.core.mathx import Transform, Vec3
from vigilia.entities.ecs import World
from vigilia.entities.systems import HitboxSyncSystem
from vigilia.player.movesets import LONGSWORD
from vigilia.model.items import Weapon


def test_volume_sync_uses_the_current_pose_and_drops_inactive_weapon() -> None:
    fighter = Fighter(0, LONGSWORD.weapon)
    fighter.attack = Attack(LONGSWORD.light[0], age=11)
    transform = Transform()
    contacts = ContactFake()
    sync = HitboxSyncSystem(contacts)
    first = evaluate_pose(transform, fighter)
    sync.sync({3: first.volumes})
    before = contacts.volumes[(3, "blade_tip")][0]
    fighter.attack.age = 16
    transform.position = Vec3(2, 0, 0)
    current = evaluate_pose(transform, fighter)
    sync.sync({3: current.volumes})
    assert contacts.volumes[(3, "blade_tip")][0] == current.bones["blade_tip"]
    assert (current.bones["blade_tip"] - before).length() > .5
    fighter.attack.age = 18
    sync.sync({3: evaluate_pose(transform, fighter).volumes})
    assert (3, "blade_tip") not in contacts.volumes


def test_same_attack_hits_once_and_invulnerability_rejects_contacts() -> None:
    world, bus, contacts = World(), EventBus(), ContactFake()
    source = Fighter(0, LONGSWORD.weapon)
    target = Fighter(1, Weapon("alvo"))
    source_transform = Transform()
    target_transform = Transform(Vec3(0, 1.25), math.pi)
    a = world.spawn(source_transform, source)
    b = world.spawn(target_transform, target)
    source.attack = Attack(LONGSWORD.light[0], age=14)
    sync = HitboxSyncSystem(contacts)
    sync.sync({a.id: evaluate_pose(source_transform, source).volumes,
               b.id: evaluate_pose(target_transform, target).volumes})
    hits = []
    bus.subscribe(DamageDealt, hits.append)
    combat = CombatSystem(contacts, PhysicsFake(), bus)
    target.invulnerable = True
    combat.resolve(world)
    assert not hits
    target.invulnerable = False
    combat.resolve(world)
    combat.resolve(world)
    assert len(hits) == 1
    assert hits[0].remaining_hp < target.max_hp


def test_world_obstacle_prevents_damage_even_if_volumes_overlap() -> None:
    world, bus, contacts, physics = World(), EventBus(), ContactFake(), PhysicsFake()
    attacker = Fighter(0, LONGSWORD.weapon)
    attacker.attack = Attack(LONGSWORD.light[0], age=14)
    a = world.spawn(Transform(), attacker)
    defender = Fighter(1, Weapon("alvo"))
    b = world.spawn(Transform(Vec3(0, 1)), defender)
    contacts.sync({(a.id, "blade_tip"): (Vec3(0, 1), .3),
                   (b.id, "torso"): (Vec3(0, 1), .3)})
    physics.wall = object()
    CombatSystem(contacts, physics, bus).resolve(world)
    assert defender.hp == defender.max_hp
