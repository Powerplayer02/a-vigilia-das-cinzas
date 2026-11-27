"""Warm-up presents an opaque cover and always removes it, without task ticks."""
from types import SimpleNamespace

from panda3d.core import NodePath
import pytest

from vigilia.engine.prewarm import prewarm_scene


class Root:
    def __init__(self,events):
        self.node=NodePath('root');self.events=events
    def attach_new_node(self,node):return self.node.attach_new_node(node)
    def prepare_scene(self,gsg):self.events.append('prepare')


def fixture(fail=False):
    events=[];root=Root(events)
    def render():
        assert not root.node.find('**/render-warmup-cover').is_empty()
        events.append('render')
        if fail:raise RuntimeError('injected GPU failure')
    app=SimpleNamespace(aspect2d=root,render=Root(events),get_aspect_ratio=lambda:16/9,
        win=SimpleNamespace(get_gsg=lambda:object()),
        graphicsEngine=SimpleNamespace(render_frame=render,sync_frame=lambda:events.append('sync')))
    return app,events


def test_cover_persists_until_resources_are_submitted_without_running_tasks():
    app,events=fixture()
    result=prewarm_scene(app)
    assert events==['render','prepare','prepare','render','render','sync']
    assert app.aspect2d.node.find('**/render-warmup-cover').is_empty()
    assert result['simulation_steps']==0


def test_cover_is_removed_after_graphics_failure():
    app,_=fixture(fail=True)
    with pytest.raises(RuntimeError):prewarm_scene(app)
    assert app.aspect2d.node.find('**/render-warmup-cover').is_empty()
