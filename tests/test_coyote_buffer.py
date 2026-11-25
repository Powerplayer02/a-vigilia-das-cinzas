from dataclasses import replace
import pytest
from advanced_fakes import scene
from test_save import full_snapshot
from vigilia.core.mathx import Vec3
from vigilia.core.types import Action, HeldState
from vigilia.save.serializers import encode,decode


@pytest.mark.parametrize('delay',[1,6,7])
def test_coyote_accepts_six_steps_after_leaving_ground_not_seven(delay):
    s=scene();s.step();s.body.on_ground=False
    for _ in range(delay-1):s.step()
    stamina=s.fighter.stamina;s.step(Action.JUMP)
    assert s.body.vertical_override==(delay<=6)
    assert stamina-s.fighter.stamina==(12 if delay<=6 else 0)
    if delay<=6:assert s.player.velocity.z==7


@pytest.mark.parametrize('delay',[1,6,7])
def test_jump_buffer_survives_six_steps_before_landing_not_seven(delay):
    s=scene();s.body.on_ground=False;s.step(Action.JUMP)
    assert not s.body.vertical_override
    for _ in range(delay-1):s.step()
    s.body.on_ground=True;s.step()
    assert s.body.jump_speed==(7 if delay<=6 else 0)
    assert s.body.vertical_override==(delay<=6)


def test_coyote_and_buffer_pending_simultaneously_trigger_only_one_jump():
    s=scene();s.step();s.body.on_ground=False
    assert s.fighter.start(s.combat.moveset.light[0])
    s.step(Action.JUMP);s.step();s.step()
    assert s.movement.coyote_age==3 and s.movement.jump_buffer_age==2
    before=s.fighter.stamina;s.fighter.attack=None;s.step()
    assert s.player.velocity.z==7 and before-s.fighter.stamina==12
    assert s.movement.coyote_age==s.movement.jump_buffer_age==-1
    s.body.on_ground=True;s.movement.vertical_speed=-.1;s.step()
    assert not s.body.vertical_override and s.fighter.stamina==before-12


def test_holding_jump_does_not_bunnyhop_on_next_landing():
    s=scene();s.step(Action.JUMP)
    before=s.fighter.stamina
    s.movement.vertical_speed=-.1;s.body.on_ground=True
    for _ in range(8):s.step(held=HeldState(frozenset({Action.JUMP})))
    assert not s.body.vertical_override and s.fighter.stamina==before


def test_no_coyote_is_created_when_spawned_in_midair():
    s=scene();s.body.on_ground=False
    s.step(Action.JUMP)
    assert s.movement.coyote_age==-1 and not s.body.vertical_override


def test_new_jump_does_not_reactivate_expired_slide_boost_from_legacy_save():
    s=scene();s.movement.air_velocity=Vec3(9,0,0);s.movement.air_steps=0
    s.step(Action.JUMP);s.step()
    assert s.player.velocity.flat()==Vec3() and s.movement.air_velocity==Vec3()


@pytest.mark.parametrize('blocked',['stamina','ceiling'])
def test_jump_buffer_cannot_bypass_stamina_or_standing_clearance(blocked):
    s=scene()
    if blocked=='stamina':s.fighter.stamina=0
    else:s.body.blocked=True
    s.step(Action.JUMP)
    for _ in range(7):s.step()
    assert not s.body.vertical_override and s.body.jump_speed==0
    s.fighter.stamina=100;s.body.blocked=False;s.step()
    assert not s.body.vertical_override


def test_roll_clears_queued_jump_before_it_can_fire_on_landing():
    s=scene();s.body.on_ground=False;s.step(Action.JUMP)
    s.step(Action.ROLL,HeldState(move_y=1));s.body.on_ground=True
    for _ in range(s.player._dodge_remaining+2):s.step()
    assert not s.body.vertical_override and s.movement.jump_buffer_age==-1


@pytest.mark.parametrize('window',['coyote','buffer'])
def test_save_roundtrip_preserves_remaining_jump_window(window):
    s=scene()
    if window=='coyote':s.step()
    s.body.on_ground=False;s.step(Action.JUMP if window=='buffer' else None);s.step()
    original=full_snapshot();snapshot=replace(original,player=replace(original.player,
        agile_movement=True,motion=s.player.to_snapshot()))
    loaded=decode(snapshot.version,snapshot.timing_version,*encode(snapshot))
    s.movement.cancel();s.player.from_snapshot(loaded.player.motion)
    assert s.player.to_snapshot()==loaded.player.motion
    if window=='buffer':s.body.on_ground=True;s.step()
    else:s.step(Action.JUMP)
    assert s.player.velocity.z==7 and s.body.vertical_override


def native_scene(position, *, ledge=False):
    from panda3d.core import NodePath
    from vigilia.engine.physics import BulletPhysicsAdapter
    from vigilia.player.advanced_movement import AdvancedMovement
    from vigilia.player.controller import PlayerController
    from vigilia.combat.fighter import Fighter
    from vigilia.model.items import LONGSWORD_SPEC
    from vigilia.core.mathx import Transform
    from vigilia.core.types import InputEdge
    physics=BulletPhysicsAdapter(NodePath('native-jump'))
    physics.add_static_box('floor',Vec3(-5 if ledge else 0,0,-.5),Vec3(10 if ledge else 20,20,1))
    body=physics.create_character(position);fighter=Fighter(0,LONGSWORD_SPEC.instantiate())
    player=PlayerController(body,Transform(position));player.advanced=AdvancedMovement(body,physics=physics)
    def step(action=None,held=HeldState()):
        player.update(held,InputEdge(action,True) if action else None,Vec3(0,1),Vec3(1,0),locked=False,fighter=fighter)
        player.apply_movement();physics.step(1/60);player.read_position()
    return body,player,step


def test_native_coyote_launches_after_capsule_has_really_left_a_ledge():
    body,player,step=native_scene(Vec3(-1,0,1.02),ledge=True)
    for _ in range(60):step()
    for _ in range(100):
        step(held=HeldState(move_x=1))
        if player.advanced.coyote_age==1:break
    assert not body.grounded() and player.advanced.coyote_age==1
    for _ in range(4):step()
    before=body.position().z;step(Action.JUMP)
    assert player.velocity.z==7 and body.vertical_override
    for _ in range(8):step()
    assert body.position().z>before+.5


def test_native_buffer_uses_landing_instead_of_requiring_a_second_keypress():
    body,player,step=native_scene(Vec3(0,0,1.5))
    while body.position().z>=1.07:step()
    assert not body.grounded()
    step(Action.JUMP)
    for _ in range(6):
        step()
        if body.vertical_override:break
    assert body.vertical_override and player.velocity.z==7
    assert player.advanced.jump_buffer_age==-1
