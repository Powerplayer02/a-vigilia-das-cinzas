"""The revised checkpoint cannot be satisfied by invalid windows or empty counters."""
from importlib.util import module_from_spec,spec_from_file_location
from pathlib import Path
import pytest

spec=spec_from_file_location('checkpoint',Path(__file__).parents[1]/'tools/check_animation_checkpoint.py')
module=module_from_spec(spec);spec.loader.exec_module(module)


def report(median=.7,p95=1.2):
    return dict(eligible_fps_baseline=True,valid_sample=True,minimized_frames=0,
        window_type='onscreen',seconds=30,warmup_seconds=5,fps_cap=60,
        scenario='final_boss_20',enemies=20,boss_phase=3,particles_min_max=[500,500],
        audio_enabled=True,median_frame_ms=16.666,animation_direct_timing=True,frames=1800,
        animation_timing=dict(render_frames=1800,animation_total_median_ms_per_render=median,
            animation_total_p95_ms_per_render=p95,direct_scopes={'fixed_step':{'calls':1800}}))


def test_within_budget_passes_and_revised_two_to_four_ms_range_is_annotated():
    assert module.validate(report())['passed']
    result=module.validate(report(2.5,3.5))
    assert result['passed'] and result['notes']


@pytest.mark.parametrize('median,p95',((4.1,4.1),(.7,4.1),(float('nan'),1.2)))
def test_excessive_or_invalid_animation_cost_cannot_pass(median,p95):
    assert not module.validate(report(median,p95))['passed']


def test_minimized_short_or_missing_fixed_step_counter_cannot_pass():
    sample=report();sample['minimized_frames']=1;sample['seconds']=29
    sample['animation_timing']['direct_scopes']={}
    assert len(module.validate(sample)['problems'])==2
