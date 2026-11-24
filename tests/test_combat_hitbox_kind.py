"""A esfera da fornalha usa os mesmos contatos e eventos que armas por osso."""

import math
from dataclasses import replace

import pytest

from boss_fakes import encounter
from combat_fakes import ContactFake, PhysicsFake
from vigilia.combat.attack import Attack, AttackKind, HitboxKind
from vigilia.combat.events import DamageDealt, HPChangedEvent
from vigilia.combat.hitbox import evaluate_pose, sphere_radius
from vigilia.combat.orchestrator import CombatSystem
from vigilia.core.mathx import Transform, Vec3
from vigilia.entities.systems import HitboxSyncSystem
from vigilia.model.items import LONGSWORD_SPEC


def resolve(e, kind, age=None, blocking=False):
    definition = e.profile.weapon.attack(kind)
    e.fighter.attack = Attack(definition, definition.windup if age is None else age)
    e.hero.blocking = blocking
    contacts = ContactFake()
    HitboxSyncSystem(contacts).sync({entity.id: evaluate_pose(pose, fighter).volumes
        for entity, (pose, fighter) in e.world.query(Transform, type(e.fighter))})
    combat = CombatSystem(contacts, PhysicsFake(), e.bus)
    combat.resolve(e.world)
    return combat, contacts


def test_default_bone_path_and_center_path_have_distinct_active_shapes():
    e = encounter()
    definition = LONGSWORD_SPEC.attacks[0]
    assert definition.hitbox_kind == HitboxKind.BONE_SPHERE
    e.hero.attack = Attack(definition, definition.windup)
    pose = evaluate_pose(Transform(), e.hero)
    assert "blade_tip" in pose.volumes and "area" not in pose.volumes
    fire = e.profile.weapon.attack(AttackKind.FIRE_AOE_RING)
    e.fighter.attack = Attack(fire, fire.windup)
    pose = evaluate_pose(Transform(Vec3(4, 5, 1)), e.fighter)
    assert pose.volumes["area"] == (Vec3(4, 5, 1), 2)
    assert "blade_tip" not in pose.volumes
    assert sphere_radius(fire, fire.windup + 29) == 6


@pytest.mark.parametrize("step,hits", [(5, False), (15, True)])
def test_expanding_fire_reaches_three_meters_at_step15_but_not_step5(step, hits):
    e = encounter(distance=3)
    resolve(e, AttackKind.FIRE_AOE_RING, age=60 + step)
    assert (e.hero.hp < e.hero.max_hp) == hits


def test_fire_hits_once_and_shield_reduces_final_damage_by_half():
    unguarded, guarded = encounter(), encounter()
    combat, _ = resolve(unguarded, AttackKind.FIRE_AOE_RING, age=75)
    combat.resolve(unguarded.world)
    resolve(guarded, AttackKind.FIRE_AOE_RING, age=75, blocking=True)
    raw = unguarded.hero.max_hp - unguarded.hero.hp
    assert raw > 0
    assert guarded.hero.max_hp - guarded.hero.hp == pytest.approx(raw * .5)


def test_grab_ignores_guard_parry_and_poise_and_knocks_down_for60_steps():
    e, hits, hp_events = encounter(distance=2), [], []
    e.bus.subscribe(DamageDealt, hits.append)
    e.bus.subscribe(HPChangedEvent, hp_events.append)
    e.hero.parry_step = 4
    resolve(e, AttackKind.FORGE_GRAB, age=45, blocking=True)
    assert hits and not hits[0].blocked
    assert e.hero.knockdown_steps == 60 and e.hero.stagger_steps == 60
    assert hp_events[0].source_kind == "enemy"
    for _ in range(60):
        e.hero.tick()
    assert e.hero.knockdown_steps == e.hero.stagger_steps == 0


def test_transition_invulnerability_rejects_real_combat_contacts():
    e = encounter(distance=1)
    e.fighter.hp = 1599
    e.bus.publish(HPChangedEvent(e.entity.id, 1600, 1599, 3200, "player"))
    attack = LONGSWORD_SPEC.attacks[0]
    e.hero.attack = Attack(attack, age=14)
    contacts = ContactFake()
    HitboxSyncSystem(contacts).sync({entity.id: evaluate_pose(pose, fighter).volumes
        for entity, (pose, fighter) in e.world.query(Transform, type(e.fighter))})
    combat = CombatSystem(contacts, PhysicsFake(), e.bus)
    for _ in range(90):
        e.boss.tick(e.world)
        combat.resolve(e.world)
        assert e.fighter.hp == 1599


def test_bullet_updates_live_sphere_radius_and_removes_inactive_shape():
    from panda3d.core import NodePath
    from vigilia.engine.physics import BulletPhysicsAdapter, BulletContactVolumes
    contacts = BulletContactVolumes(BulletPhysicsAdapter(NodePath("boss-test")))
    source, target = (1, "area"), (2, "body_center")
    for radius, hit in [(2, False), (4, True), (2, False), (6, True)]:
        contacts.sync({source: (Vec3(), radius), target: (Vec3(0, 3), .05)})
        assert contacts.overlaps(source, (target,)) == hit
    contacts.sync({target: (Vec3(0, 3), .05)})
    assert not contacts.overlaps(source, (target,))


def test_phase2_riposte_window_allows_four_hits_then_closes():
    from vigilia.combat.events import StaggerTriggered
    e, hits = encounter(distance=1), []
    e.boss.phase = 2
    e.bus.publish(StaggerTriggered(e.entity.id, False))
    e.bus.subscribe(DamageDealt, hits.append)
    contacts = ContactFake()
    contacts.sync({(e.player.id, "blade_tip"): (Vec3(), .2), (e.entity.id, "torso"): (Vec3(), .3)})
    combat = CombatSystem(contacts, PhysicsFake(), e.bus)
    definition = LONGSWORD_SPEC.attack(AttackKind.RIPOSTE)
    for remaining in (3, 2, 1, 0):
        e.hero.attack = Attack(definition, definition.windup, victim=e.entity.id)
        combat.resolve(e.world)
        assert hits[-1].critical == "riposte"
        assert e.fighter.riposte_hits_remaining == remaining
    assert e.fighter.riposte_steps == 0
