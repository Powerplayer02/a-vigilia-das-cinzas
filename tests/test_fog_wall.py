"""Entrada de arena e barreira Bullet independentes do módulo de IA."""

import pytest

from combat_fakes import PhysicsFake
from vigilia.core.events import EventBus, BossArenaEnteredEvent, BossDefeatedEvent
from vigilia.core.mathx import Vec3
from vigilia.model.world_state import WorldState
from vigilia.world.fog_wall import FogWall


def wall():
    bus, collider = EventBus(), PhysicsFake()
    fog = FogWall("warden", "forge_arena", Vec3(0, 13, 2), Vec3(0, 15, 1), collider, WorldState(), bus)
    return fog, bus, collider


def test_barrier_stays_closed_until_defeat_and_entry_publishes_core_event():
    fog, bus, collider = wall()
    events = []
    bus.subscribe(BossArenaEnteredEvent, events.append)
    assert collider.active and not events
    with pytest.raises(ValueError):
        fog.cross(Vec3(5, 10, 1))
    fog.cross(Vec3(0, 12, 1))
    assert events == [BossArenaEnteredEvent("warden", "forge_arena", Vec3(0, 15, 1))]
    assert collider.active and fog.in_fight
    with pytest.raises(ValueError):
        fog.cross(Vec3(0, 12, 1))


def test_defeat_event_removes_only_matching_barrier():
    fog, bus, collider = wall()
    bus.publish(BossDefeatedEvent("other", 10))
    assert collider.active
    bus.publish(BossDefeatedEvent("warden", 2400))
    assert not collider.active
    fog.state.defeated_bosses.add("warden")
    fog.sync()
    assert not fog.blocked and not fog.can_enter(Vec3(0, 12, 1))


def test_removable_bullet_barrier_blocks_raycast_then_allows_passage():
    from panda3d.core import NodePath
    from vigilia.engine.physics import BulletPhysicsAdapter
    physics = BulletPhysicsAdapter(NodePath("fog-test"))
    obstacle = physics.add_static_box("fog", Vec3(0, 2, 1), Vec3(4, .3, 3))
    assert physics.raycast(Vec3(0, 0, 1), Vec3(0, 4, 1)) is not None
    obstacle.set_active(False)
    assert physics.raycast(Vec3(0, 0, 1), Vec3(0, 4, 1)) is None
    obstacle.set_active(True)
    assert physics.raycast(Vec3(0, 0, 1), Vec3(0, 4, 1)) is not None


def test_open_fog_connects_navigation_under_the_overhead_lintel():
    from vigilia.ai.pathfinding import a_star
    from vigilia.world.arena import nav_grid
    start, end = Vec3(0, 12, 1), Vec3(0, 16, 1)
    assert not a_star(nav_grid(), start, end)
    assert a_star(nav_grid(fog_closed=False), start, end)
