"""Direct animation timings keep per-step/per-render costs and nesting separate."""
from importlib.util import module_from_spec,spec_from_file_location
from pathlib import Path
from types import SimpleNamespace
import pytest

spec=spec_from_file_location('animation_timing',Path(__file__).parents[1]/'tools/animation_timing.py')
module=module_from_spec(spec);spec.loader.exec_module(module)


def test_animation_cost_does_not_double_count_the_outer_presentation_scope():
    now=[0.]
    def work():now[0]+=.001
    renderer=SimpleNamespace(animate_actor=work,combat_pose=work)
    game=SimpleNamespace(_renderer=renderer,_evaluate_poses=work,_animation_view=work,
        _fixed_step=work,_particles=SimpleNamespace(update=work))
    def draw():game._animation_view();renderer.animate_actor();renderer.combat_pose()
    game._draw_combat=draw
    timer=module.AnimationTiming(game,clock=lambda:now[0]);timer.begin()
    timer.begin_render();game._fixed_step();game._evaluate_poses();game._evaluate_poses()
    game._particles.update();game._draw_combat();timer.end_render()
    result=timer.report()
    # 2 logical steps +1 view +1 mixer; exclude the nested3ms outer scope.
    assert result['animation_total_mean_ms_per_render']==pytest.approx(4.)
    assert result['animation_total_median_ms_per_render']==pytest.approx(4.)
    assert result['animation_total_p95_ms_per_render']==pytest.approx(4.)
    assert result['direct_scopes']['fixed_step']['median_ms']==pytest.approx(1.)
    assert result['direct_scopes']['particles']['p95_ms']==pytest.approx(1.)
    assert result['animation_inclusive_median_ms_per_render']==pytest.approx(5.)
    assert result['stages']['presentation']['mean_ms_per_call']==pytest.approx(3.)
    assert result['stages']['authoritative_pose']['calls']==2
