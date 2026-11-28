"""Native particle gallery and preserved-state checks; no performance/balance claim."""
import argparse
import json
import math
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from panda3d.core import Filename,PNMImage,ClockObject
from vigilia.core.config import Config
from vigilia.core.mathx import Vec3
from vigilia.engine.app import ArenaApp
from vigilia.engine.particles import PRESETS,MAX_PARTICLES
from vigilia.engine.particle_scene import AREA_EFFECTS
from vigilia.engine.diagnostics import build_fingerprint
from vigilia.combat.events import HPChangedEvent
from vigilia.game import Game
from verify_animations import verify_dynamic_particle_buffers


def verify_light_clock(game,app,position):
    renderer=game._renderer;root=renderer.root;clock=app._clock
    original_glow=renderer._fire_glow_value
    clock_input=root.get_shader_input('light_clock')
    original_clock=tuple(clock_input.get_vector())[:3]
    mode,dt,now=clock.get_mode(),clock.get_dt(),clock.get_frame_time()
    try:
        root.set_shader_input('fire_glow',(position.x,position.y,position.z,4))
        root.set_shader_input('light_clock',(0,0,0))
        state=int(root.get_state().this)
        clock.set_mode(ClockObject.M_non_real_time);clock.set_dt(.001);clock.set_frame_time(0);clock.tick()
        app.graphicsEngine.render_frame();app.graphicsEngine.render_frame()
        dark=PNMImage();assert app.win.get_screenshot(dark)
        clock.set_dt(math.pi/18);clock.tick()
        app.graphicsEngine.render_frame();app.graphicsEngine.render_frame()
        bright=PNMImage();assert app.win.get_screenshot(bright)
        assert int(root.get_state().this)==state
        assert (bright.get_average_xel()-dark.get_average_xel()).length()>1e-6, (tuple(dark.get_average_xel()),tuple(bright.get_average_xel()),clock.get_frame_time())
        root.set_shader_input('light_clock',(0,clock.get_frame_time(),1))
        app.graphicsEngine.render_frame();app.graphicsEngine.render_frame()
        frozen_before=PNMImage();assert app.win.get_screenshot(frozen_before)
        clock.set_dt(.4);clock.tick()
        app.graphicsEngine.render_frame();app.graphicsEngine.render_frame()
        frozen=PNMImage();assert app.win.get_screenshot(frozen)
        assert (frozen.get_average_xel()-frozen_before.get_average_xel()).length()<1e-6
    finally:
        clock.set_mode(mode);clock.set_dt(dt);clock.set_frame_time(now)
        root.set_shader_input('fire_glow',original_glow)
        root.set_shader_input('light_clock',original_clock)


def verify(output):
    output.mkdir(parents=True,exist_ok=True)
    rows=[]
    with tempfile.TemporaryDirectory(prefix='vigilia-particles-') as temp:
        app=ArenaApp(Config(vsync=False),window_type='offscreen')
        try:
            game=Game(app,Config(),ROOT/'assets',save_path=Path(temp)/'save.sqlite3',front_end=True,enemy_count=0)
            app.start(game)
            for area in AREA_EFFECTS:
                if area!=game.active_area:game.change_area(area,stash=False,restore=False)
                assert len(game._particles.pool.slots)==MAX_PARTICLES
                # Exercise the composed frame too (dt0 cannot advance rules).
                game.frame(0.,(0,0),(0,0))
                before=game.build_snapshot();pool=game._particles
                geometry_ids=[int(node.node().get_geom(0).this) for node in pool.nodes]
                shader_id=int(pool.root.get_shader().this)
                position=game._transform.position
                if game.ui_backend:game.ui_backend.root.hide()
                for node in (game._renderer._plate,game._renderer._boss_hud,
                    game._renderer._combat_text,game._renderer._target_text):node.hide()
                game._polish.overlay.hide()
                app.camera.set_pos(position.x+5,position.y+5,position.z+3)
                app.camera.look_at(position.x,position.y,position.z)
                verify_light_clock(game,app,position)
                for _ in range(120):
                    game._particle_scene.update(1/60,position);pool.update(1/60,position)
                for variant in ('ambient','combat'):
                    if variant=='combat':
                        pool.spawn('blood',position+Vec3(-1,1,.3));pool.spawn('sparks',position+Vec3(1,1,.5))
                        pool.spawn('shockwave',position-Vec3(0,0,.8))
                        pool.spawn('souls',position+Vec3(2,3,1));pool.spawn('level',position)
                        pool.update(.12,position)
                    app.graphicsEngine.render_frame();app.graphicsEngine.render_frame()
                    filename=f'{area}-{variant}.png'
                    app.win.get_screenshot().write(Filename.from_os_specific(str((output/filename).resolve())))
                    assert game.build_snapshot()==before
                    rows.append(dict(area=area,variant=variant,screenshot=filename,active=pool.pool.active_count,
                        light_updates_pixels_without_root_state_churn=True,
                        light_freezes_on_pause=True,
                        snapshot_preserved=True,dynamic_buffers_connected=verify_dynamic_particle_buffers(pool)))
                # Force the real HP transition event without stepping combat.
                if game.boss is not None:
                    for fraction in ((.45,.2) if game.boss.profile.phase3_threshold else (.45,)):
                        old=game.boss.fighter.hp;game.boss.fighter.hp=game.boss.profile.max_hp*fraction
                        game._bus.publish(HPChangedEvent(game.boss.entity.id,old,game.boss.fighter.hp,game.boss.profile.max_hp,'fixture'))
                        before_phase=game.build_snapshot()
                        game._renderer.prepare_phase_resources();app.graphicsEngine.render_frame()
                        assert game.build_snapshot()==before_phase and game.boss.transition_remaining==90
                        assert geometry_ids==[int(node.node().get_geom(0).this) for node in pool.nodes]
                        assert shader_id==int(pool.root.get_shader().this)
                        center=game._position(game.boss.entity.id)
                        app.camera.set_pos(center.x+4,center.y-7,center.z+3)
                        app.camera.look_at(center.x,center.y,center.z)
                        pool.update(.12,center)
                        app.graphicsEngine.render_frame();app.graphicsEngine.render_frame()
                        phase_image=f'{area}-phase{game.boss.phase}.png'
                        app.win.get_screenshot().write(Filename.from_os_specific(str((output/phase_image).resolve())))
                        rows.append(dict(area=area,phase=game.boss.phase,transition_steps=90,
                            screenshot=phase_image,
                            snapshot_preserved=True,shared_particle_geometry_shader=True,
                            dynamic_buffers_connected=verify_dynamic_particle_buffers(pool)))
            report=dict(kind='Native offscreen functional/gallery fixture, not performance or human playtest',
                source_build_id=build_fingerprint(ROOT),capacity=MAX_PARTICLES,presets=list(PRESETS),rows=rows)
            (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
            return report
        finally:app.destroy()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=verify(args.output)
    print(json.dumps(dict(capacity=result['capacity'],checks=len(result['rows']))))
