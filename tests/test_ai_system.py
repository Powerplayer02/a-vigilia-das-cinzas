"""FSM, combate e navegação dos três perfis com portas simuladas."""

import math

import pytest

from combat_fakes import ContactFake, PhysicsFake
from vigilia.ai.ai_system import AISystem
from vigilia.combat.attack import Attack
from vigilia.combat.events import ParrySucceeded
from vigilia.combat.fighter import Fighter
from vigilia.combat.orchestrator import CombatSystem, DeathSystem
from vigilia.core.events import EventBus
from vigilia.core.mathx import Transform, Vec3
from vigilia.core.navigation import NavGrid
from vigilia.core.timing import PATROL_IDLE_STEPS, REPATH_INTERVAL_STEPS
from vigilia.core.types import AIMode, RayHit
from vigilia.entities.archetypes import make_enemy
from vigilia.entities.components import AIStateComponent, AttackIntent, MovementIntent, BodyRef
from vigilia.entities.ecs import World
from vigilia.model.enemies import ENEMIES
from vigilia.model.items import LONGSWORD_SPEC


def scenario(profile_id="cinzeiro", distance=1.5):
    world, physics = World(), PhysicsFake()
    target = world.spawn(Transform(Vec3(5.5, 5.5, 1)), Fighter(0, LONGSWORD_SPEC.instantiate()))
    profile = ENEMIES[profile_id]
    position = Vec3(5.5, 5.5 + distance, 1)
    body = PhysicsFake()
    body.teleport(position)
    enemy = make_enemy(world, profile.id, position, body,
                       Fighter(1, profile.weapon.instantiate(), profile.stats),
                       (position, position + Vec3(2, 0)))
    grid = NavGrid(tuple((True,) * 30 for _ in range(30)), 1, Vec3(0, 0, 1))
    ai = AISystem(grid, physics, target)
    combat = CombatSystem(ContactFake(), physics, EventBus())
    return world, physics, target, enemy, ai, combat


def test_idle_patrol_timer_and_detection_respects_los() -> None:
    world, physics, target, enemy, ai, combat = scenario(distance=5)
    physics.wall = object()
    state = world.get(enemy, AIStateComponent)
    for _ in range(PATROL_IDLE_STEPS - 1):
        ai.tick(world)
    assert state.mode == AIMode.IDLE
    ai.tick(world)
    assert state.mode == AIMode.PATROL
    physics.wall = None
    ai.tick(world)
    assert state.mode == AIMode.CHASE


@pytest.mark.parametrize("profile_id", tuple(ENEMIES))
def test_all_profiles_attack_recover_and_use_zero_stamina_cost(profile_id) -> None:
    world, physics, target, enemy, ai, combat = scenario(profile_id, distance=6 if ENEMIES[profile_id].ranged else 1.4)
    state, fighter = world.get(enemy, AIStateComponent), world.get(enemy, Fighter)
    modes, attacks = [], []
    previous = None
    for _ in range(250):
        ai.tick(world)
        intent = world.get(enemy, AttackIntent)
        if intent.definition is not None:
            attacks.append(intent.definition.kind)
        combat.consume_intents(world)
        fighter.tick()
        if state.mode != previous:
            modes.append(state.mode)
            previous = state.mode
    assert AIMode.ATTACK_WINDUP in modes and AIMode.RECOVER in modes
    assert fighter.stamina == fighter.stats.max_stamina
    if profile_id == "rancor":
        assert len(set(attacks)) == 2


@pytest.mark.parametrize("profile_id", tuple(key for key, p in ENEMIES.items() if p.attacks[0].parryable))
def test_parry_interrupts_every_profile_through_shared_fighter(profile_id) -> None:
    world, physics, target, enemy, ai, _ = scenario(profile_id, distance=1.4)
    fighter = world.get(enemy, Fighter)
    pose = world.get(enemy, Transform)
    pose.yaw = math.pi
    victim = world.get(target, Fighter)
    victim.parry_step = 11
    definition = ENEMIES[profile_id].attacks[0]
    fighter.attack = Attack(definition, definition.windup, aim=Vec3(5.5, 5.5, 1.2))
    contacts = ContactFake()
    contacts.sync({
        (enemy.id, "blade_mid"): (Vec3(5.5, 6, 1.2), .2),
        (target.id, "shield"): (Vec3(5.5, 6, 1.2), .38),
        (target.id, "torso"): (Vec3(5.5, 5.5, 1.2), .32),
    })
    bus, events = EventBus(), []
    bus.subscribe(ParrySucceeded, events.append)
    CombatSystem(contacts, physics, bus).resolve(world)
    assert events
    assert fighter.attack is None and fighter.stagger_steps == 90
    ai.tick(world)
    assert world.get(enemy, AIStateComponent).mode == AIMode.STAGGERED
    assert world.get(enemy, MovementIntent).velocity == Vec3()


def test_stagger_timer_expires_and_dead_body_is_removed() -> None:
    world, physics, target, enemy, ai, _ = scenario()
    fighter = world.get(enemy, Fighter)
    fighter.interrupt(24)
    for _ in range(24):
        ai.tick(world)
        assert world.get(enemy, AIStateComponent).mode == AIMode.STAGGERED
        fighter.tick()
    ai.tick(world)
    assert world.get(enemy, AIStateComponent).mode == AIMode.CHASE
    fighter.hp = 0
    ai.tick(world)
    DeathSystem().tick(world)
    assert world.get(enemy, AIStateComponent).mode == AIMode.DEAD
    assert not world.get(enemy, BodyRef).body.active
    ai.reset(world)
    DeathSystem().tick(world)
    assert fighter.alive and world.get(enemy, BodyRef).body.active
    assert world.get(enemy, AIStateComponent).mode == AIMode.IDLE


def test_melee_navigation_follows_path_around_a_pillar() -> None:
    world, physics, target, enemy, ai, _ = scenario(distance=7)
    rows = tuple(tuple(not (4 <= x <= 6 and 8 <= y <= 9) for x in range(20)) for y in range(20))
    ai.grid = NavGrid(rows, 1, Vec3(0, 0, 1))
    transform = world.get(enemy, Transform)
    for _ in range(240):
        ai.tick(world)
        intent = world.get(enemy, MovementIntent)
        position = transform.position + intent.velocity * (1 / 60)
        assert ai.grid.walkable(ai.grid.to_cell(position))
        transform.position = position
    assert transform.position.y < 8


def test_hitscan_respects_obstacle_and_fires_only_once() -> None:
    world, physics, target, enemy, ai, _ = scenario("bestario", distance=5)
    fighter, victim = world.get(enemy, Fighter), world.get(target, Fighter)
    definition = ENEMIES["bestario"].attacks[0]
    fighter.attack = Attack(definition, definition.windup, aim=Vec3(5.5, 5.5, 1.2))
    contacts = ContactFake()
    contacts.sync({(target.id, "torso"): (Vec3(5.5, 5.5, 1.2), .32)})
    combat = CombatSystem(contacts, physics, EventBus())
    combat.resolve(world)
    hp = victim.hp
    assert hp < victim.max_hp
    combat.resolve(world)
    assert victim.hp == hp
    fighter.attack = Attack(definition, definition.windup, aim=Vec3(5.5, 5.5, 1.2))
    physics.wall = RayHit(Vec3(5.5, 9, 1.2), Vec3(0, 1), 1)
    combat.resolve(world)
    assert victim.hp == hp


def test_chase_can_approach_player_in_conservative_wall_margin() -> None:
    world, physics, target, enemy, ai, combat = scenario(distance=7)
    rows = tuple(tuple(x > 0 for x in range(20)) for _ in range(20))
    ai.grid = NavGrid(rows, 1, Vec3(0, 0, 1))
    world.get(target, Transform).position = Vec3(.8, 5.5, 1)
    for _ in range(20):
        ai.tick(world)
    assert world.get(enemy, MovementIntent).velocity.length() > 0


def test_repath_requests_stay_distributed_when_target_moves_after_long_idle():
    world, physics, target, first, ai, _ = scenario(distance=15)
    ai.grid = NavGrid(tuple((True,) * 60 for _ in range(60)), 1, Vec3(0, 0, 1))
    profile = ENEMIES["cinzeiro"]
    for index in range(19):
        position = Vec3(20 + index % 5, 20 + index // 5, 1)
        make_enemy(world, profile.id, position, PhysicsFake(),
                   Fighter(1, profile.weapon.instantiate(), profile.stats), (position,))
    for _, (state,) in world.query(AIStateComponent):
        state.alerted = True
    for _ in range(60):
        ai.tick(world)
    world.get(target, Transform).position += Vec3(2, 0)
    counts = []
    for _ in range(REPATH_INTERVAL_STEPS):
        before = ai.path_count
        ai.tick(world)
        counts.append(ai.path_count - before)
    assert sum(counts) == 20
    assert max(counts) <= 2
