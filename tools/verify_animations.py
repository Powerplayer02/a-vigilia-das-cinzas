"""Native visual fixtures and invariants, not a human playthrough."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from panda3d.core import Filename
from vigilia.core.animation import AnimationView
from vigilia.core.config import Config
from vigilia.core.mathx import Transform,Vec3
from vigilia.engine.app import ArenaApp
from vigilia.engine.animation import WARMUP_CLIPS
from vigilia.combat.hitbox import evaluate_pose
from vigilia.combat.fighter import Fighter
from vigilia.game import Game
from vigilia.entities.components import EnemyTag
from vigilia.entities.ecs import Entity
from vigilia.model.items import WEAPONS
from vigilia.engine.diagnostics import build_fingerprint


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--area',choices=('patio_da_vigilia','pantano_das_cinzas','forno_da_vigilia'),default='patio_da_vigilia')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='vigilia-animation-') as temp:
        app=ArenaApp(Config(vsync=False),window_type='offscreen')
        try:
            game=Game(app,Config(),ROOT/'assets',save_path=Path(temp)/'save.sqlite3',front_end=True,enemy_count=3)
            app.start(game)
            if args.area!='patio_da_vigilia':game.change_area(args.area,stash=False,restore=False,stress_enemies=3)
            snapshot=game.build_snapshot();rng=game._particles.pool._rng.getstate()
            transforms=[(node,node.get_transform()) for row in game._renderer._animation_nodes.values()
                for node in (row[0],row[1],row[2],*row[3],*row[4:])]
            warmup=game._renderer.warmup_animations()
            assert game.build_snapshot()==snapshot
            assert rng==game._particles.pool._rng.getstate()
            assert all(node.get_transform()==value for node,value in transforms)
            results=dict(kind='Native visual fixture; no human gameplay claim',warmup=warmup,
                source_build_id=build_fingerprint(ROOT),
                area=args.area,boss=game.boss.profile.id,
                snapshot_preserved=True,transforms_preserved=True,visual_rng_preserved=True,clips=list(WARMUP_CLIPS),screenshots=[])
            renderer=game._renderer
            renderer.statics.hide()
            for node in renderer._flames:node.hide()
            for node in renderer._gates.values():node.hide()
            for node in renderer._dummies.values():node.hide()
            for node in renderer._targets.values():node.hide()
            for node in (renderer._plate,renderer._boss_hud,renderer._combat_text,renderer._target_text):node.hide()
            if game.ui_backend:game.ui_backend.root.hide()
            actor_ids=[game._entity.id]+[e.id for e in game._enemies]+[game.boss.entity.id]
            roots=[renderer._player]+[renderer._enemies[i][0] for i in actor_ids[1:]]
            for identity,gear in renderer._combat_gear.items():
                if identity not in actor_ids:
                    for node in gear:node.hide()
            app.camera.set_pos(0,10,3.5);app.camera.look_at(0,0,.3)
            renderer.root.set_shader_input('eye_pos',app.camera.get_pos())
            renderer._box(renderer.root,'gallery-floor',Vec3(0,0,-.1),Vec3(12,8,.2),(.25,.29,.32,1))
            cases=['idle','walk','run','roll_left','roll_back','light_1:windup','light_1:active',
                'heavy:active','parry','drink','wall_cling','slamming','phase','death_front',
                'slow_overhead:active','wide_sweep:active','forge_grab:active','fire_aoe_ring:active']
            for index,clip in enumerate(cases):
                for offset,(identity,root) in enumerate(zip(actor_ids,roots)):
                    position=Vec3((offset-2)*1.65,0,1.02)
                    root.show();root.set_pos(position.x,position.y,position.z);root.set_h(0)
                    actual=game._world.get(Entity(identity),Fighter)
                    tag=game._world.get(Entity(identity),EnemyTag)
                    fake=Fighter(actual.team,actual.weapon,actual.stats)
                    fake.body_scale=actual.body_scale
                    actual_clip=clip
                    if ':' in clip:
                        definitions=WEAPONS[actual.weapon.spec_id].attacks
                        definition=next((a for a in definitions if a.kind.value==clip.split(':')[0]),definitions[index%len(definitions)])
                        actual_clip=definition.kind.value+':'+clip.split(':')[1]
                        fake.start(definition)
                        fake.attack.age=definition.windup+(definition.active//2 if clip.endswith(':active') else -max(1,definition.windup//2))
                    pose=evaluate_pose(Transform(position),fake)
                    view=AnimationView(actual_clip,.65,5.8,profile=tag.profile_id if tag else 'boss:'+game.boss.profile.id if identity==game.boss.entity.id else 'player',phase=3)
                    renderer._frame_dt=.2
                    renderer.animate_actor(identity,view)
                    renderer.combat_pose(identity,pose.bones,axe=False,alive=not clip.startswith('death'),
                        hit=False,telegraph=clip.endswith(':windup'),weapon_style=actual.weapon.spec_id)
                app.graphicsEngine.render_frame();app.graphicsEngine.render_frame()
                path=args.output/f'{index:02}-{clip.replace(":","-")}.png'
                app.win.get_screenshot().write(Filename.from_os_specific(str(path.resolve())))
                results['screenshots'].append(path.name)
            assert game.build_snapshot()==snapshot
            results['snapshot_preserved_after_gallery']=True
            # Real transition event/queue: test preparation without stepping rules.
            from vigilia.combat.events import HPChangedEvent
            phase_checks=[]
            for fraction in (.45,.2) if game.boss.profile.phase3_threshold else (.45,):
                old_hp=game.boss.fighter.hp;game.boss.fighter.hp=game.boss.profile.max_hp*fraction
                game._bus.publish(HPChangedEvent(game.boss.entity.id,old_hp,game.boss.fighter.hp,game.boss.profile.max_hp,'fixture'))
                before=game.build_snapshot();rng=game._particles.pool._rng.getstate()
                renderer.prepare_phase_resources();app.graphicsEngine.render_frame()
                assert game.build_snapshot()==before
                assert game._particles.pool._rng.getstate()==rng
                phase_checks.append(dict(phase=game.boss.phase,snapshot_preserved=True,
                    transition_steps_remaining=game.boss.transition_remaining,
                    queued_native_resources=sum(getattr(app.win.get_gsg().get_prepared_objects(),'get_num_queued_'+kind)()
                        for kind in ('shaders','textures','vertex_buffers','index_buffers'))))
            results['phase_preparation']=phase_checks
            (args.output/'report.json').write_text(json.dumps(results,indent=2),encoding='utf8')
        finally:app.destroy()


if __name__=='__main__':main()
