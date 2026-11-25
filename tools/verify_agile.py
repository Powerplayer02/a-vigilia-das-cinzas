"""Native stage-1 smoke; synthetic inputs, not a manual balance playthrough."""
from contextlib import ExitStack
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from panda3d.core import Filename
from vigilia.core.config import Config
from vigilia.core.events import DashStartedEvent, SlideStartedEvent, SaveRequestedEvent
from vigilia.core.mathx import Vec3,Transform
from vigilia.core.views import UICommand,UICommandKind as C
from vigilia.engine.app import ArenaApp
from vigilia.game import Game
from vigilia.save.serializers import encode,decode


def main():
    out=ROOT/'artifacts/5.5/agile';out.mkdir(parents=True,exist_ok=True)
    app=ArenaApp(Config(vsync=False),window_type='offscreen')
    try:
        with tempfile.TemporaryDirectory(prefix='vigilia-agile-') as directory,ExitStack() as cleanup:
            base=Path(directory)
            game=Game(app,Config(vsync=False),ROOT/'assets',save_path=base/'game.db',
                settings_path=base/'options.toml',enemy_count=0)
            cleanup.callback(game.close)
            app.start(game);app.taskMgr.remove('vigilia-update')
            def frames(n=1):
                for _ in range(n):game.frame(1/60,(0,0),(0,0))
            def warp(point):
                game._player.body.teleport(point);game._transform.position=point;game._previous=Transform(point)
            def option():
                error=game.execute(UICommand(C.SET_OPTION,json.dumps(dict(key='ultrakill_style',delta=1))))
                assert error==game.localizer.t('common.saved'),error
            assert game._player.advanced is None and not hasattr(game._renderer,'_dash_trails')
            game.open_menu('pause');option()
            assert game._player.advanced is not None and len(game._renderer._dash_trails)==16
            game.execute(UICommand(C.RESUME));warp(Vec3(0,-6,1.02));frames(30)
            game._toggle_lock();target=game._target;assert target is not None
            events=[]
            game._bus.subscribe(DashStartedEvent,events.append);game._bus.subscribe(SlideStartedEvent,events.append)
            game.keyboard('w',True);frames();game.keyboard('alt',True);frames(4)
            assert game._fighter.invulnerable and game._player.advanced.charges==1
            assert game._target==target
            app.graphicsEngine.render_frame()
            assert app.win.save_screenshot(Filename.from_os_specific(str(out/'dash.png')))
            saved=game.build_snapshot();assert saved.player.agile_movement
            assert decode(saved.version,saved.timing_version,*encode(saved))==saved
            game.open_menu('pause');option()
            assert game._player.advanced is None and not game.build_snapshot().player.agile_movement
            game.apply_snapshot(saved)
            assert game._player.advanced.to_snapshot()==saved.player.motion.advanced
            assert game._commands.movement is game._player.advanced
            game.execute(UICommand(C.RESUME));game.input.reset();frames(15)
            warp(Vec3(-7,-5,1.02));game._target=None;game._camera.set_target(None);frames(30)
            game.keyboard('w',True);game.keyboard('shift',True);frames(3);game.keyboard('v',True)
            for _ in range(5):
                frames()
                if game._player.advanced.sliding:break
            assert game._player.advanced.sliding and game._player.body.crouched
            assert not game._fighter.invulnerable
            app.graphicsEngine.render_frame();app.graphicsEngine.render_frame()
            assert app.win.save_screenshot(Filename.from_os_specific(str(out/'slide.png')))
            z=game._transform.position.z
            game.keyboard('b',True);frames(12)
            assert not game._player.body.crouched and game._transform.position.z>z+.4
            game.input.reset();frames(120)
            game.open_menu('pause')
            game._bus.publish(SaveRequestedEvent(1,'equipment'));game._flush_save()
            on=game._save.load(1)
            assert on.player.agile_movement
            option()
            off=game.build_snapshot();assert not off.player.agile_movement
            game.apply_snapshot(on);assert game._player.advanced is not None
            game.apply_snapshot(off);assert game._player.advanced is None
            result=dict(native_bullet=True,mode_off_has_no_controller_or_visual_pool=True,
                dash_iframes=True,lock_preserved=True,mid_dash_roundtrip=True,slide_capsule_half=True,
                slide_jump=True,mode_saved_per_character=True,off_after_loading_off_save=True,
                audio_events=[type(e).__name__ for e in events],manual_balance_certified=False)
            (out/'native.json').write_text(json.dumps(result,indent=2),encoding='utf8')
            print(json.dumps(result))
    finally:app.destroy()


if __name__=='__main__':main()
