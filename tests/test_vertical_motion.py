from dataclasses import replace
import pytest
from panda3d.core import NodePath
from vigilia.core.mathx import Vec3
from vigilia.engine.physics import BulletPhysicsAdapter
from vigilia.save.serializers import encode,decode,SaveFormatError
from test_save import full_snapshot
from test_wall_jump import airborne
from test_slam import dropping
from vigilia.core.types import Action,HeldState
from vigilia.player.advanced_movement import AdvancedMovement
from vigilia.combat.fighter import Fighter
from vigilia.model.items import LONGSWORD_SPEC
from vigilia.core.events import SlamImpactEvent


def body():
    physics=BulletPhysicsAdapter(NodePath('vertical-test'))
    physics.add_static_box('floor',Vec3(0,0,-.5),Vec3(20,20,1))
    character=physics.create_character(Vec3(0,0,4));physics.step(1/60)
    return physics,character


def test_native_motor_freezes_old_fall_and_slam_has_exact_vertical_speed():
    world,character=body();character.override_vertical(True)
    before=character.position();character.set_velocity(Vec3())
    for _ in range(24):world.step(1/60)
    assert character.position().z==pytest.approx(before.z,abs=1e-5)
    character.set_velocity(Vec3(0,0,-18));world.step(1/60)
    assert character.position().z-before.z==pytest.approx(-.3,abs=1e-5)


def test_native_exit_restores_gravity_and_does_not_leave_a_second_active_body():
    world,character=body();character.override_vertical(True);air=character.node
    assert world._world.get_num_characters()==1
    character.override_vertical(False);character.set_velocity(Vec3())
    assert character.node!=air and character.node.get_gravity()==20
    for _ in range(180):world.step(1/60)
    assert character.grounded() and character.position().z==pytest.approx(.85,abs=.01)
    character.override_vertical(True)
    assert character.node==air and world._world.get_num_characters()==1


@pytest.mark.parametrize('support',['actor','dummy','ledge'])
def test_slam_finishes_on_character_only_colliders_and_capsule_edge(support):
    physics=BulletPhysicsAdapter(NodePath('slam-support'))
    if support=='actor':
        physics.add_static_box('floor',Vec3(0,0,-.5),Vec3(20,20,1))
        physics.create_character(Vec3(0,0,.85))
    elif support=='dummy':
        physics.add_static_box('dummy',Vec3(0,0,.9),Vec3(.8,.8,1.8),camera_collision=False)
    else:
        physics.add_static_box('ledge',Vec3(-1,0,0),Vec3(2,2,1))
    x=.2 if support=='ledge' else 0
    character=physics.create_character(Vec3(x,0,4))
    physics.step(1/60)
    events=[];movement=AdvancedMovement(character,physics=physics,emit=events.append)
    fighter=Fighter(0,LONGSWORD_SPEC.instantiate())
    from vigilia.core.types import InputEdge
    for step in range(40):
        result=movement.step(HeldState(),InputEdge(Action.SLAM,True) if step==0 else None,
            Vec3(0,1),Vec3(1,0),fighter,character.position())
        if result:character.set_velocity(result.velocity)
        physics.step(1/60)
        if movement.mode=='slam_recovery':break
    assert movement.mode=='slam_recovery'
    assert len([event for event in events if isinstance(event,SlamImpactEvent)])==1
    assert character.grounded()


@pytest.mark.parametrize('mode',['wall_cling','wall_jump','slam','slam_recovery'])
def test_vertical_modes_timers_and_wall_history_roundtrip_without_retrigger(mode):
    if mode.startswith('wall'):
        s=airborne();s.step(held=HeldState(move_y=1))
        if mode=='wall_jump':s.step(Action.JUMP)
    else:
        s=dropping();s.step(Action.SLAM)
        if mode=='slam_recovery':s.player.transform.position=Vec3(0,0,1);s.step()
    original=full_snapshot()
    snapshot=replace(original,player=replace(original.player,agile_movement=True,
        motion=s.player.to_snapshot()))
    loaded=decode(snapshot.version,snapshot.timing_version,*encode(snapshot))
    assert loaded==snapshot
    s.movement.cancel();s.player.from_snapshot(loaded.player.motion)
    assert s.player.to_snapshot()==loaded.player.motion and s.body.vertical_override


def test_corrupt_vertical_state_cannot_activate_air_motor_in_a_legacy_save():
    original=full_snapshot();s=airborne();s.step(held=HeldState(move_y=1))
    with pytest.raises(SaveFormatError):encode(replace(original,player=replace(original.player,
        motion=s.player.to_snapshot())))
    state=replace(s.movement.to_snapshot(),vertical_speed=float('inf'))
    with pytest.raises(SaveFormatError):encode(replace(original,player=replace(original.player,
        agile_movement=True,motion=replace(s.player.to_snapshot(),advanced=state))))
