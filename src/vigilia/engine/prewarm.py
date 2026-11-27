"""Submit already-created scene resources while a black cover is presented.

This does not step the application or claim to prepare future, uncreated assets.
It is first-use mitigation, not a diagnosis of the historical render stall.
"""
import time

from panda3d.core import CardMaker


def prewarm_scene(app, *, samples=(), static_scene=None):
    started=time.perf_counter()
    card=CardMaker('render-warmup-cover')
    aspect=app.get_aspect_ratio()
    card.set_frame(-aspect,aspect,-1,1)
    cover=app.aspect2d.attach_new_node(card.generate())
    cover.set_color(0,0,0,1)
    cover.set_bin('fixed',2000)
    cover.set_depth_test(False)
    cover.set_depth_write(False)
    render_calls=0
    try:
        app.graphicsEngine.render_frame()
        render_calls+=1
        gsg=app.win.get_gsg()
        # Premunge replaces Geoms. Keep externally updated particle buffers out
        # of that destructive walk; prepare_scene and the sample renders still
        # prepare them through the ordinary GSG cache.
        (static_scene if static_scene is not None else app.render).premunge_scene(gsg)
        app.aspect2d.premunge_scene(gsg)
        app.render.prepare_scene(gsg)
        app.aspect2d.prepare_scene(gsg)
        # prepare_scene enqueues resources in1.10.16; render consumes the queue.
        app.graphicsEngine.render_frame()
        app.graphicsEngine.render_frame()
        render_calls+=2
        for apply_sample in samples:
            apply_sample()
            app.graphicsEngine.render_frame()
            render_calls+=1
        app.graphicsEngine.sync_frame()
    finally:
        cover.remove_node()
    return dict(milliseconds=(time.perf_counter()-started)*1000,
        render_calls=render_calls,simulation_steps=0,scope='Already-created render/UI resources only')
