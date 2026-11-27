"""Submit already-created scene resources while a black cover is presented.

This does not step the application or claim to prepare future, uncreated assets.
It is first-use mitigation, not a diagnosis of the historical render stall.
"""
import time

from panda3d.core import CardMaker


def prewarm_scene(app):
    started=time.perf_counter()
    card=CardMaker('render-warmup-cover')
    aspect=app.get_aspect_ratio()
    card.set_frame(-aspect,aspect,-1,1)
    cover=app.aspect2d.attach_new_node(card.generate())
    cover.set_color(0,0,0,1)
    cover.set_bin('fixed',2000)
    cover.set_depth_test(False)
    cover.set_depth_write(False)
    try:
        app.graphicsEngine.render_frame()
        gsg=app.win.get_gsg()
        app.render.prepare_scene(gsg)
        app.aspect2d.prepare_scene(gsg)
        # prepare_scene enqueues resources in1.10.16; render consumes the queue.
        app.graphicsEngine.render_frame()
        app.graphicsEngine.render_frame()
        app.graphicsEngine.sync_frame()
    finally:
        cover.remove_node()
    return dict(milliseconds=(time.perf_counter()-started)*1000,
        render_calls=3,simulation_steps=0,scope='Already-created render/UI resources only')
