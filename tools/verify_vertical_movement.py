"""Stage-2 native functional smoke; positions/timers are QA seeds, not balance."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from panda3d.core import Filename,PNMImage,ClockObject
from vigilia.engine.app import ArenaApp
from vigilia.game import Game
from vigilia.core.config import Config
from vigilia.core.mathx import Vec3,Transform
from vigilia.core.events import WallClingStartedEvent,WallJumpStartedEvent,SlamImpactEvent
from vigilia.combat.events import DamageDealt
from vigilia.combat.fighter import Fighter
from vigilia.core.types import AppState


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/5.5/stage2/native')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    app=ArenaApp(Config(vsync=False),window_type='offscreen')
    try:
        with tempfile.TemporaryDirectory(prefix='vigilia-vertical-') as directory,ExitStack() as cleanup:
            root=Path(directory)
            game=Game(app,Config(vsync=False),ROOT/'assets',save_path=root/'test.db',
                settings_path=root/'prefs.toml',enemy_count=0)
            cleanup.callback(game.close);app.start(game);app.taskMgr.remove('vigilia-update')
            app._clock.set_mode(ClockObject.M_non_real_time);app._clock.set_dt(1/60)
            app.graphicsEngine.render_frame();app.graphicsEngine.render_frame()
            monitor=game.enable_diagnostics(args.output/'spikes',report_path=args.output/'diagnostics.json')
            pending=[];images=[]
            def update(task):
                for operation in pending[:]:operation()
                pending.clear();game.frame(1/60,(0,0),(0,0))
                return task.cont
            app.taskMgr.add(update,'vertical-smoke-step',sort=10)
            def frames(count=1):
                for _ in range(count):app.taskMgr.step()
            def act(operation):
                pending.append(operation);frames()
            def warp(point):
                game._player.body.teleport(point);game._transform.position=point;game._previous=Transform(point)
            def capture(name):
                image=PNMImage();assert app.win.get_screenshot(image)
                images.append((name,image))
            assert game._player.advanced is None
            game.keyboard('g',True);assert game.input.next_edge() is None;game.input.reset()
            act(lambda:game._configure_agile(True));game._practice_wait=100000
            events=[];damage=[]
            for kind in (WallClingStartedEvent,WallJumpStartedEvent,SlamImpactEvent):
                game._bus.subscribe(kind,events.append)
            game._bus.subscribe(DamageDealt,damage.append)
            warp(Vec3(-10.65,-8,2.5));game._camera._yaw=0
            game.keyboard('a',True)
            for _ in range(8):
                frames()
                if game._player.advanced.mode=='wall_cling':break
            assert game._player.advanced.mode=='wall_cling'
            frozen=game._transform.position;frames(8)
            cling_drift=(game._transform.position-frozen).length()
            assert cling_drift<.01
            capture('wall-cling')
            before=game.build_snapshot();act(lambda:game._save.save(1,before))
            act(game._player.advanced.cancel);act(lambda:game.apply_snapshot(game._save.load(1)))
            assert game._player.advanced.mode=='wall_cling' and game._player.body.vertical_override
            game.input.reset();game.keyboard('b',True);frames()
            assert game._player.velocity.x>0 and game._player.velocity.z>0
            launch=game._transform.position;frames(8)
            assert game._transform.position.x>launch.x+.3 and game._transform.position.z>launch.z+.4
            capture('wall-jump')
            assert len([e for e in events if isinstance(e,WallClingStartedEvent)])==1
            game._player.advanced.cancel();game.input.reset()
            warp(Vec3(0,2.4,4));frames(2)
            target=game._practice_target
            game._target=target;game._update_target()
            game.keyboard('g',True);frames()
            assert game._player.advanced.mode=='slam' and not game._fighter.invulnerable
            slam_before=game.build_snapshot();act(lambda:game._save.save(1,slam_before))
            act(game._player.advanced.cancel);act(lambda:game.apply_snapshot(game._save.load(1)));game.input.reset()
            assert game._player.advanced.mode=='slam'
            # apply_snapshot resets lock normally; this lock must persist through the impact.
            game._target=target;game._update_target()
            for _ in range(30):
                frames()
                if game._player.advanced.mode=='slam_recovery':break
            assert game._player.advanced.mode=='slam_recovery'
            assert game._target==target and len([e for e in events if isinstance(e,SlamImpactEvent)])==1
            assert any(e.attack_kind=='slam' and e.target==target.id for e in damage)
            capture('slam-impact')
            hp=game._world.get(target,Fighter).hp
            saved=game.build_snapshot();act(lambda:game.apply_snapshot(saved));frames(9)
            assert game._world.get(target,Fighter).hp==hp
            assert not game._player.body.vertical_override and game._player.body.node.get_gravity()==20
            act(lambda:game._configure_agile(False))
            assert not game.build_snapshot().player.agile_movement
            monitor.close()
            for name,image in images:
                assert image.write(Filename.from_os_specific(str(args.output/(name+'.png'))))
            result=dict(native_wall_cling=True,cling_drift_m=cling_drift,
                cling_snapshot=True,wall_jump_away=True,slam_snapshot=True,
                slam_damage=True,impact_count=1,recovery_reload_did_not_repeat_damage=True,
                lock_preserved=True,gravity_restored=True,mode_off=True,
                landed_on_target=True,
                qa_seeds=['Teleport to wall and directly above training target','Training attack timer disabled'],
                manual_balance_certified=False,build_id=monitor.build_id,
                diagnostics=monitor.report(),png_encoding='after instrumented frames')
            (args.output/'vertical.json').write_text(json.dumps(result,indent=2),encoding='utf8')
            print(json.dumps(result))
            if monitor.quarantined:
                raise RuntimeError('QA build quarantined; inspect diagnostics.json and profiles')
    finally:app.destroy()


if __name__=='__main__':main()
