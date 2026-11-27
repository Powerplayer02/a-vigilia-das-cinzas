"""The GPU fixture records poses actually applied, excluding wooden targets."""
from importlib.util import module_from_spec,spec_from_file_location
from pathlib import Path
from types import SimpleNamespace
from vigilia.core.animation import AnimationView

spec=spec_from_file_location('animation_workload',Path(__file__).parents[1]/'tools/animation_workload.py')
module=module_from_spec(spec);spec.loader.exec_module(module)


def test_fixture_covers_actual_pose_and_leaves_unrigged_targets_out(monkeypatch):
    renderer=SimpleNamespace(_animation_mixers={0:SimpleNamespace(action='',cue_remaining=.3)})
    calls=[]
    def animate(identity,view):
        calls.append(identity)
        if identity in renderer._animation_mixers:renderer._animation_mixers[identity].action=view.action
    renderer.animate_actor=animate
    workload=module.AnimationWorkload(renderer)
    monkeypatch.setattr(module.time,'perf_counter',lambda:10.)
    workload.begin()
    renderer.animate_actor(0,AnimationView(profile='boss:fixture'))
    renderer.animate_actor(99,AnimationView(profile='dummy'))
    assert calls==[0,99] and workload.calls==1
    assert workload.seen=={'boss:fixture':{'1:idle'}}
    assert renderer._animation_mixers[0].cue_remaining==0
