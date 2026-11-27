"""Compare real logical activation with the peak of applied native rig poses.

Headless: no window, GPU timing, input injection or user save. Measures the
pose submitted to the scene graph, not compositor/display latency.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from panda3d.core import NodePath,Point3
from vigilia.core.mathx import Transform,Vec3
from vigilia.core.timing import FIXED_DT
from vigilia.core.types import GameState
from vigilia.combat.fighter import Fighter
from vigilia.combat.hitbox import evaluate_pose,WEAPON_BONES
from vigilia.entities.components import MovementIntent
from vigilia.entities.ecs import World
from vigilia.engine.animation import AnimationMixer,ATTACKS
from vigilia.engine.render import ArenaRenderer,_unit_cube
from vigilia.game import Game
from vigilia.model.bosses import load_boss_profile


def cases():
    for name in ('warden','tide','custodian'):
        profile=load_boss_profile(ROOT/f'data/bosses/{name}.toml',register=False)
        for phase in range(1,4 if profile.phase3_threshold else 3):
            for attack in profile.weapon.attacks:yield profile,phase,attack


def measure(profile,phase,definition,*,keep_trace=False):
    world=World()
    player=world.spawn(Transform())
    fighter=Fighter(1,profile.weapon.instantiate(),profile.stats)
    fighter.body_scale=1.8
    x0,y0,x1,y1=profile.bounds
    transform=Transform(Vec3((x0+x1)/2,(y0+y1)/2,1.02),.37)
    entity=world.spawn(transform,fighter,MovementIntent())
    game=Game.__new__(Game);game._world=world;game._entity=player
    game.boss=SimpleNamespace(entity=entity,profile=profile,phase=phase,intro_remaining=0,transition_remaining=0)
    game._app=SimpleNamespace(state=GameState.PLAYING)
    game._has_session=True
    renderer=ArenaRenderer.__new__(ArenaRenderer)
    renderer.root=NodePath('scene');renderer._cube=_unit_cube()
    actor=renderer.root.attach_new_node('actor');actor.set_scale(1.8)
    actor.set_pos(transform.position.x,transform.position.y,transform.position.z)
    actor.set_h(-math.degrees(transform.yaw))
    rig=actor.attach_new_node('rig');torso=rig.attach_new_node('torso');head=rig.attach_new_node('head')
    limbs=tuple(rig.attach_new_node(name) for name in ('left-arm','left-leg','right-arm','right-leg'))
    knees=(limbs[1].attach_new_node('knee'),limbs[3].attach_new_node('knee'))
    renderer._animation_nodes={entity.id:(rig,torso,head,limbs,limbs[0],limbs[2],*knees)}
    renderer._animation_mixers={entity.id:AnimationMixer()}
    renderer._animation_props={entity.id:rig.attach_new_node('prop')}
    renderer._animation_applied={};renderer._enemies={entity.id:(actor,rig,limbs)};renderer._frame_dt=FIXED_DT
    renderer._combat_gear={};renderer._gear_styles={};renderer._dummies={}
    renderer.shadows=SimpleNamespace(pose=lambda *args:None)
    # Define the visible strike direction geometrically, independent of its age.
    target=ATTACKS[definition.kind.value][1]
    direction=target[:8]+target[10:]
    norm=sum(v*v for v in direction)
    trace=[];first_active=first_volume=None;weapon_error=0.;weapon_checks=0
    assert fighter.start(definition)
    while fighter.attack is not None:
        age=fighter.attack.age
        logical=fighter.attack.active
        logical_pose=evaluate_pose(transform,fighter)
        volumes=logical_pose.volumes
        weapon_live=bool(set(volumes).intersection((*WEAPON_BONES,'area')))
        if logical and first_active is None:first_active=age
        if weapon_live and first_volume is None:first_volume=age
        # Production resolves contacts, ticks Fighter, then builds the render
        # view. Keep that ordering: the render view may be one step ahead.
        fighter.tick()
        render_age=fighter.attack.age if fighter.attack is not None else None
        renderer.animate_actor(entity.id,game._animation_view(entity,fighter))
        renderer.combat_pose(entity.id,logical_pose.bones,axe=True,alive=True,hit=False,
            telegraph=bool(fighter.attack and fighter.attack.age<definition.windup),
            ranged=definition.ranged,weapon_style=profile.weapon.id)
        if logical:
            weapon=renderer._combat_gear[entity.id][0]
            for name,fraction in (('blade_inner',.28),('blade_mid',.63),('blade_tip',1.)):
                actual=renderer.root.get_relative_point(weapon,Point3(0,fraction-.5,0))
                expected=logical_pose.bones[name]
                error=math.sqrt((actual.x-expected.x)**2+(actual.y-expected.y)**2+(actual.z-expected.z)**2)
                weapon_error=max(weapon_error,error);weapon_checks+=1
        values=(rig.get_p(),rig.get_r(),rig.get_h(),rig.get_z(),torso.get_p(),head.get_p(),
            limbs[1].get_p(),limbs[3].get_p(),knees[0].get_p(),knees[1].get_p())
        strength=sum(a*b for a,b in zip(values,direction))/max(1,norm)
        trace.append(dict(age=age,render_attack_age=render_age,active=logical,weapon_volume=weapon_live,visual_strength=strength,
            applied_pose=list(values)))
    peak=max(trace,key=lambda row:row['visual_strength'])['age']
    offset=peak-first_active
    result=dict(boss=profile.id,phase=phase,attack=definition.kind.value,
        declared_in_phase_moveset=definition in profile.moveset(phase),
        windup_steps=definition.windup,active_steps=definition.active,
        first_active_age=first_active,first_weapon_volume_age=first_volume,
        activation_source='Attack.active (ranged emission)' if definition.ranged else 'CombatPose weapon/area volume',
        visual_peak_age=peak,offset_steps=offset,offset_ms=round(offset*FIXED_DT*1000,6),
        weapon_points_checked=weapon_checks,max_weapon_point_error=weapon_error,
        passed=abs(offset)<=2 and weapon_error<.0001 and (definition.ranged or first_volume==first_active))
    if keep_trace:result['trace']=trace
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    rows=[measure(*case,keep_trace=True) for case in cases()]
    report=dict(tolerance_steps=2,tolerance_ms=FIXED_DT*2000,
        logical_source='Attack.active and evaluate_pose contact volumes before Fighter.tick',
        visual_source='Native NodePath transforms after Fighter.tick and ArenaRenderer.animate_actor at60Hz',
        implementation_hashes={name:hashlib.sha256((ROOT/'src/vigilia'/name).read_bytes()).hexdigest()
            for name in ('engine/animation.py','core/animation.py','game.py','combat/hitbox.py')},
        limitation='Scene-graph pose timing, not GPU/compositor/display latency or human legibility.',
        passed=all(row['passed'] for row in rows),cases=rows)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(dict(passed=report['passed'],cases=len(rows),
        failures=sum(not row['passed'] for row in rows),max_offset_steps=max(abs(r['offset_steps']) for r in rows))))
    raise SystemExit(0 if report['passed'] else 1)


if __name__=='__main__':main()
