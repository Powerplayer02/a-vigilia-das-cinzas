import pytest
from advanced_fakes import scene
from vigilia.core.mathx import Vec3
from vigilia.core.types import Action, HeldState
from vigilia.model.attacks import AttackKind

SLIDING = HeldState(frozenset({Action.RUN,Action.SLIDE}),move_y=1)


def test_slide_requires_running_movement_ground_and_stamina():
    for ground, held, stamina in [(False,SLIDING,100),(True,HeldState(move_y=1),100),(True,SLIDING,0)]:
        s = scene(); s.body.on_ground=ground; s.fighter.stamina=stamina
        s.step(Action.SLIDE,held)
        assert not s.movement.sliding and not s.body.crouched


def test_slide_decelerates_36_steps_has_no_iframes_and_restores_capsule():
    s = scene(); initial=s.fighter.stamina
    speeds=[s.step(Action.SLIDE,SLIDING).length()]
    for _ in range(35):
        assert not s.fighter.invulnerable
        speeds.append(s.step(held=SLIDING).length())
    assert speeds[0] == pytest.approx(5.8*1.4)
    assert all(a>b for a,b in zip(speeds,speeds[1:]))
    assert not s.movement.sliding and not s.body.crouched
    assert initial-s.fighter.stamina == 14


def test_releasing_slide_or_dashing_restores_normal_capsule():
    for action in (None,Action.DASH):
        s = scene(); s.step(Action.SLIDE,SLIDING)
        s.step(action,HeldState(move_y=1))
        assert not s.movement.sliding and not s.body.crouched


def test_slide_jump_preserves_direction_with_twenty_percent_speed_boost():
    s=scene(); speed=s.step(Action.SLIDE,SLIDING).length()
    velocity=s.step(Action.JUMP,SLIDING)
    assert not s.movement.sliding and not s.body.crouched and s.body.jump_speed==7
    assert velocity.y == pytest.approx(speed*(35/36)*1.2)
    assert not s.fighter.invulnerable


def test_slide_light_attack_uses_distinct_moveset_and_cost():
    s=scene();s.step(Action.SLIDE,SLIDING)
    s.step(Action.LIGHT,SLIDING)
    attack=s.fighter.attack.definition
    assert attack.kind == AttackKind.SLIDING
    assert (attack.windup,attack.active,attack.recovery,attack.stamina)==(9,5,20,18)
    assert s.movement.sliding and not s.fighter.invulnerable


def test_stagger_cancels_slide_but_low_ceiling_prevents_expanding_capsule():
    s=scene();s.step(Action.SLIDE,SLIDING)
    s.body.blocked=True;s.fighter.stagger_steps=8
    s.step()
    assert not s.movement.sliding and s.body.crouched and not s.fighter.invulnerable
    s.body.blocked=False;s.fighter.stagger_steps=0;s.step()
    assert not s.body.crouched


def test_bullet_half_height_cache_headroom_and_wall_collision():
    from panda3d.core import NodePath
    from vigilia.engine.physics import BulletPhysicsAdapter
    world=BulletPhysicsAdapter(NodePath('slide-physics'))
    world.add_static_box('geometry', Vec3(0,0,-.5),Vec3(20,20,1))
    world.add_static_box('geometry', Vec3(0,0,1.4),Vec3(2,2,.4))
    body=world.create_character(Vec3(-3,0,1.02))
    for _ in range(90):world.step(1/60)
    original=body.node
    assert body.set_crouched(True)
    low=body.node
    total_height=2*low.get_shape().get_half_height()+2*body.radius
    assert total_height==pytest.approx(body.height*.5)
    body.teleport(Vec3(0,0,body.position().z))
    world.step(1/60)
    assert not body.set_crouched(False) and body.node==low
    body.teleport(Vec3(-3,0,1.02))
    assert body.set_crouched(False) and body.node==original
    assert body.set_crouched(True) and body.node==low
    world.add_static_box('geometry', Vec3(-1,0,1),Vec3(.3,4,2))
    body.set_velocity(Vec3(25,0,0))
    for _ in range(30):world.step(1/60)
    assert body.position().x < -1.4


def test_bullet_slide_jump_gains_height_after_restoring_capsule():
    from panda3d.core import NodePath
    from vigilia.engine.physics import BulletPhysicsAdapter
    world=BulletPhysicsAdapter(NodePath('jump-physics'))
    world.add_static_box('geometry', Vec3(0,0,-.5),Vec3(20,20,1))
    body=world.create_character(Vec3(0,0,1.02))
    for _ in range(90):world.step(1/60)
    body.set_crouched(True);world.step(1/60)
    assert body.set_crouched(False)
    before=body.position().z
    assert body.jump(7)
    for _ in range(12):world.step(1/60)
    assert body.position().z > before+.5
