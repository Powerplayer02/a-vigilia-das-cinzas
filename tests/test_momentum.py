from dataclasses import replace, asdict
import inspect
from pathlib import Path
import hashlib
import json

import pytest
from advanced_fakes import scene
from test_slide import SLIDING
from test_wall_jump import airborne
from test_save import full_snapshot
from vigilia.core.mathx import Vec3
from vigilia.core.types import Action, HeldState, InputEdge
from vigilia.model.attacks import AttackKind
from vigilia.model.items import WEAPONS, PLAYER_WEAPON_IDS
from vigilia.combat.damage import resolve_damage
from vigilia.save.serializers import encode, decode, SaveFormatError


def dashed():
    s=scene();s.step(Action.DASH)
    for _ in range(11):s.step()
    return s


def test_dash_tail_is_continuous_then_decays_linearly_for_twenty_four_steps():
    s=dashed();tail=s.player.velocity
    carried=[s.step() for _ in range(24)]
    assert carried[0]==tail and carried[-1]==tail*(1/24)
    assert all(a.y>b.y>0 for a,b in zip(carried,carried[1:]))
    assert sum(v.y/60 for v in carried)==pytest.approx(tail.y*12.5/60)
    assert s.step()==Vec3() and s.movement.momentum_remaining==0
    assert not s.fighter.invulnerable


def test_release_of_slide_preserves_its_last_velocity_instead_of_stopping():
    s=scene();last=s.step(Action.SLIDE,SLIDING)
    assert s.step()==last and not s.movement.sliding and not s.body.crouched
    for _ in range(23):s.step()
    assert s.step()==Vec3()


@pytest.mark.parametrize('step',[1,24,25,30])
def test_dash_attack_window_covers_first_and_last_step_but_not_thirtieth(step):
    s=dashed()
    for _ in range(step-1):s.step()
    s.step(Action.LIGHT)
    expected=AttackKind.DASH_ATTACK if step<=24 else AttackKind.LIGHT_1
    assert s.fighter.attack.definition.kind==expected
    if step<=24:assert s.player.velocity.y>0


def test_attacking_cancels_dash_without_losing_its_current_velocity():
    s=scene();last=s.step(Action.DASH)
    assert s.step(Action.LIGHT)==last
    assert not s.movement.dashing and not s.fighter.invulnerable
    assert s.fighter.attack.definition==s.combat.moveset.dash_attack


def test_attack_after_release_of_slide_uses_slide_variant_and_keeps_motion():
    s=scene();s.step(Action.SLIDE,SLIDING);s.step()
    before=s.player.velocity.length();s.step(Action.LIGHT)
    assert s.fighter.attack.definition==s.combat.moveset.slide_attack
    assert 0<s.player.velocity.length()<before


def test_directional_input_blends_toward_walking_without_adding_two_speeds():
    s=dashed();start=s.player.velocity.length();held=HeldState(move_x=1)
    speeds=[s.step(held=held).length() for _ in range(24)]
    assert max(speeds)<=start and s.step(held=held)==Vec3(3.1,0,0)


def test_roll_replaces_momentum_through_its_last_step_and_does_not_restore_it():
    s=dashed();s.step(Action.ROLL,HeldState(move_x=1))
    assert s.player.dodging and s.player.velocity.y==0
    assert s.movement.momentum_remaining==0
    for _ in range(s.player._dodge_remaining):
        s.step(Action.DASH)
        assert s.player.velocity.y==0 and not s.movement.dashing
    assert s.step()==Vec3() and s.movement.momentum_source==''


@pytest.mark.parametrize('kind',[AttackKind.RIPOSTE,AttackKind.BACKSTAB])
def test_critical_keeps_accepted_stationary_pose_instead_of_coasting_through_victim(kind):
    s=dashed();edge=InputEdge(Action.LIGHT,True)
    s.combat.update(HeldState(),edge,Vec3(0,1),dodging=False,critical=(7,Vec3(0,1),kind))
    s.player.update(HeldState(),edge,Vec3(0,1),Vec3(1,0),locked=False,fighter=s.fighter,busy=True)
    assert s.fighter.attack.definition.kind==kind and s.player.velocity==Vec3()
    assert not s.movement.momentum_remaining


@pytest.mark.parametrize('carried',[False,True])
def test_cling_zeros_horizontal_momentum_and_wall_jump_only_uses_its_own_impulse(carried):
    s=dashed() if carried else scene()
    s.body.on_ground=False;s.movement.physics=airborne().movement.physics
    s.step(held=HeldState(move_y=1))
    assert s.movement.mode=='wall_cling' and s.player.velocity==Vec3()
    assert not s.movement.momentum_remaining and s.movement.momentum_velocity==Vec3()
    v=s.step(Action.JUMP)
    assert v.flat()==Vec3(0,-5.8,0) and v.z>0


def test_coasting_into_wall_without_held_direction_still_clings():
    s=dashed();s.body.on_ground=False;s.movement.physics=airborne().movement.physics
    s.step()
    assert s.movement.mode=='wall_cling' and not s.movement.momentum_remaining


@pytest.mark.parametrize('weapon_id',PLAYER_WEAPON_IDS)
def test_moveset_damage_order_is_baked_in_for_all_weapons(weapon_id):
    spec=WEAPONS[weapon_id]
    def damage(kind):
        return resolve_damage(spec.attack(kind).packet,spec.requirements,spec,
            spec.requirements,full_snapshot().player.fighter.resist).hp
    assert damage(AttackKind.DASH_ATTACK)>damage(AttackKind.SLIDING)>damage(AttackKind.RUNNING)
    assert damage(AttackKind.RUNNING)>damage(AttackKind.WALKING_ATTACK)>damage(AttackKind.LIGHT_1)
    assert spec.attack(AttackKind.DASH_ATTACK).cancel_from is None


def test_damage_function_and_signature_are_unchanged_from_accepted_stage_two():
    # This is the accepted pure damage module, not a reimplementation of its formula.
    source=Path(inspect.getfile(resolve_damage)).read_bytes().replace(b'\r\n',b'\n')
    assert hashlib.sha256(source).hexdigest()=='c53e01d0a2e4127e1ab5b844f30331d1695f7cbfe1268ae4f226f5f3634bbc33'
    assert 'momentum' not in inspect.signature(resolve_damage).parameters


@pytest.mark.parametrize('attack',[False,True])
def test_momentum_and_attack_survive_snapshot_without_restarting_window(attack):
    s=dashed();s.step()
    if attack:s.step(Action.LIGHT)
    original=full_snapshot()
    # The fixture owns/upgrades an axe; match it before serializing a live attack.
    s.combat.equip(WEAPONS['axe'].instantiate(2))
    if attack:
        s.fighter.attack=None;s.step(Action.LIGHT)
    snapshot=replace(original,player=replace(original.player,agile_movement=True,
        motion=s.player.to_snapshot(),fighter=replace(original.player.fighter,
            attack=s.fighter.to_snapshot({}).attack if attack else None)))
    loaded=decode(snapshot.version,snapshot.timing_version,*encode(snapshot))
    assert loaded==snapshot
    expected=s.step();remaining=s.movement.momentum_remaining
    s.player.from_snapshot(loaded.player.motion)
    assert s.step()==expected and s.movement.momentum_remaining==remaining


@pytest.mark.parametrize('values',[{'momentum_remaining':25},{'momentum_source':'run'},
    {'momentum_velocity':Vec3(0,0,1)},{'coyote_age':7},{'jump_buffer_age':True}])
def test_corrupt_momentum_and_window_fields_are_rejected(values):
    s=dashed();original=full_snapshot()
    motion=replace(s.player.to_snapshot(),advanced=replace(s.movement.to_snapshot(),**values))
    with pytest.raises(SaveFormatError):encode(replace(original,player=replace(original.player,
        agile_movement=True,motion=motion)))


def test_stage_two_save_without_new_fields_and_with_old_slide_packet_remains_readable():
    s=scene();s.step(Action.SLIDE,SLIDING);s.step(Action.LIGHT,SLIDING)
    original=full_snapshot();s.combat.equip(WEAPONS['axe'].instantiate(2))
    s.fighter.attack=None;s.step(Action.LIGHT,SLIDING)
    snapshot=replace(original,player=replace(original.player,agile_movement=True,
        motion=s.player.to_snapshot(),fighter=replace(original.player.fighter,attack=s.fighter.to_snapshot({}).attack)))
    player,world=encode(snapshot);data=json.loads(player)
    for key in ('momentum_velocity','momentum_remaining','momentum_source','last_horizontal','coyote_age','jump_buffer_age'):
        del data['motion']['advanced'][key]
    data['fighter']['attack']['definition']['packet']=asdict(WEAPONS['axe'].attack(AttackKind.LIGHT_1).packet)
    loaded=decode(snapshot.version,snapshot.timing_version,json.dumps(data),world)
    assert loaded.player.motion.advanced.momentum_remaining==0
    assert loaded.player.motion.advanced.jump_buffer_age==-1
    assert loaded.player.fighter.attack.definition.packet==WEAPONS['axe'].attack(AttackKind.LIGHT_1).packet
