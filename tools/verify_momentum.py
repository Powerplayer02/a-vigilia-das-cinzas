"""Stage-3 native Game smoke with deterministic QA seeds, not a balance playthrough."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from panda3d.core import ClockObject
from vigilia.core.config import Config
from vigilia.core.mathx import Vec3,Transform
from vigilia.engine.app import ArenaApp
from vigilia.game import Game
from vigilia.model.attacks import AttackKind


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/5.5/stage3/native')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    app=ArenaApp(Config(vsync=False),window_type='offscreen')
    try:
        with tempfile.TemporaryDirectory(prefix='vigilia-momentum-') as directory,ExitStack() as cleanup:
            game=Game(app,Config(vsync=False),ROOT/'assets',save_path=Path(directory)/'test.db',
                settings_path=Path(directory)/'prefs.toml',enemy_count=0)
            cleanup.callback(game.close);app.start(game);app.taskMgr.remove('vigilia-update')
            app._clock.set_mode(ClockObject.M_non_real_time);app._clock.set_dt(1/60)
            app.graphicsEngine.render_frame();app.graphicsEngine.render_frame()
            monitor=game.enable_diagnostics(args.output/'spikes',report_path=args.output/'diagnostics.json')
            pending=[]
            def update(task):
                for operation in pending[:]:operation()
                pending.clear();game.frame(1/60,(0,0),(0,0))
                return task.cont
            app.taskMgr.add(update,'momentum-smoke-step',sort=10)
            def frames(count=1):
                for _ in range(count):app.taskMgr.step()
            def act(operation):pending.append(operation);frames()
            def warp(point):
                game._player.body.teleport(point);game._transform.position=point;game._previous=Transform(point)
            act(lambda:game._configure_agile(True));game._practice_wait=100000;game._camera._yaw=0
            warp(Vec3(0,-6,1.02));frames(20)
            game.keyboard('alt',True);frames(12);game.input.reset()
            movement=game._player.advanced
            assert not movement.dashing and movement.momentum_remaining==24
            tail=game._player.velocity;start=game._transform.position
            saved=game.build_snapshot()
            # Loading takes one simulation step; the timer must advance, not restart.
            act(lambda:game.apply_snapshot(saved));movement=game._player.advanced
            assert movement.momentum_remaining==23 and (game._player.velocity-tail).length()<1e-6
            frames(23)
            displacement=(game._transform.position-start).flat().length()
            assert abs(displacement-tail.length()*12.5/60)<.03
            frames();assert game._player.velocity.flat().length()<.001
            # Early attack inherits the peak speed and selects its own definition.
            warp(Vec3(0,-6,1.02));game.input.reset();game.keyboard('alt',True);frames()
            peak=game._player.velocity;game.keyboard('mouse1',True);frames()
            assert game._fighter.attack.definition.kind==AttackKind.DASH_ATTACK
            assert (game._player.velocity-peak).length()<1e-5 and not game._fighter.invulnerable
            # Roll cancels the carry instead of restoring it after its fixed motion.
            game._fighter.attack=None;game.input.reset();game.keyboard('d',True);game.keyboard('space',True);frames(2)
            assert game._player.dodging and not game._player.advanced.momentum_remaining
            game.input.reset();frames(game._player._dodge_remaining+1)
            assert game._player.velocity.flat().length()<.001
            # Real ledge exit; the sixth coyote step is used after save/load.
            game._player.advanced.cancel();game.input.reset();game._camera._yaw=0
            game._physics.add_static_box('qa-coyote-platform',Vec3(-5,-5,2),Vec3(2,4,.5))
            warp(Vec3(-5,-5,3.1));frames(20);game.keyboard('d',True)
            for _ in range(100):
                frames()
                if game._player.advanced.coyote_age==1:break
            assert game._player.advanced.coyote_age==1 and not game._player.body.grounded()
            game.input.reset();frames(3);saved=game.build_snapshot()
            assert saved.player.motion.advanced.coyote_age==4
            act(lambda:game.apply_snapshot(saved))
            assert game._player.advanced.coyote_age==5
            game.keyboard('b',True);frames();game.input.reset()
            assert game._player.velocity.z==7 and game._player.body.vertical_override
            launch_z=game._transform.position.z;frames(8)
            assert game._transform.position.z>launch_z+.5
            # Queue a jump during an actual fall, before native Bullet reports ground.
            game._player.advanced.cancel();game.input.reset();warp(Vec3(4,-6,1.5));frames(2)
            for _ in range(30):
                if game._transform.position.z<1.07:break
                frames()
            assert not game._player.body.grounded()
            game.keyboard('b',True);frames();game.input.reset()
            buffered=game._player.advanced.jump_buffer_age
            assert buffered==0 and not game._player.body.vertical_override
            for _ in range(6):
                frames()
                if game._player.body.vertical_override:break
            assert game._player.velocity.z==7 and game._player.advanced.jump_buffer_age==-1
            jump=game.build_snapshot();act(lambda:game.apply_snapshot(jump))
            assert game._player.body.vertical_override and game._player.advanced.jump_buffer_age==-1
            act(lambda:game._configure_agile(False))
            assert game._player.advanced is None and not game._player.body.vertical_override
            monitor.close()
            report=dict(build_id=monitor.build_id,native_game=True,dash_tail_distance_m=round(displacement,6),
                momentum_roundtrip=True,dash_attack_inherits_speed=True,roll_clears_momentum=True,
                sixth_step_coyote_after_reload=True,buffered_landing_jump=True,jump_snapshot=True,
                mode_off_restores_gravity=True,manual_balance_certified=False,
                qa_seeds=['Temporary ledge and teleports','Training attack timer disabled'],diagnostics=monitor.report())
            (args.output/'momentum.json').write_text(json.dumps(report,indent=2),encoding='utf8')
            print(json.dumps(report))
            if monitor.quarantined:raise RuntimeError('QA build quarantined; inspect diagnostics')
    finally:app.destroy()


if __name__=='__main__':main()
