"""The release gate rejects invalid sampling and frame-time regressions."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

spec=spec_from_file_location('render_gate',Path(__file__).parents[1]/'tools/check_render_performance.py')
module=module_from_spec(spec)
spec.loader.exec_module(module)


def reports():
    common=dict(valid_sample=True,minimized_frames=0,eligible_fps_baseline=True,
        qa_diagnostics=False,window_type='onscreen',seconds=60.01,warmup_seconds=5,
        scenario='final_boss_20',enemies=20,particles_min_max=[500,500],
        renderer='dedicatedGPU',resolution=[1280,720],contact_shadow_quality='medium',
        audio_enabled=True,agile_movement_enabled=False,benchmark_seed=37,hud='full',gc_mode='normal')
    return {name:dict(common,fps_cap=60 if name.endswith('_capped') else 0,
        median_frame_ms=16.666 if name.endswith('_capped') else 3.5,
        p95_frame_ms=16.72 if name.endswith('_capped') else 6.6,
        fps=60 if name.endswith('_capped') else 240)
        for name in ('baseline_capped','candidate_capped','baseline_uncapped','candidate_uncapped')}


def test_equal_gpu_controls_pass_with_linear_frame_time_units():
    data=reports()
    data['candidate_uncapped']['median_frame_ms']+=.2
    assert module.validate(data)['passed']


def test_minimized_short_or_wrong_workload_is_never_a_fps_baseline():
    for field,value in (('minimized_frames',1),('seconds',10),('particles_min_max',[0,500]),('eligible_fps_baseline',False)):
        data=reports()
        data['candidate_capped'][field]=value
        assert not module.validate(data)['passed']


def test_cap_or_uncapped_tail_regression_blocks_publication_gate():
    for key,field,value in (('candidate_capped','median_frame_ms',17),
            ('candidate_uncapped','median_frame_ms',4.1),('candidate_uncapped','p95_frame_ms',7.7)):
        data=reports(); data[key][field]=value
        assert not module.validate(data)['passed']


def test_animation_budget_does_not_reuse_the_smaller_hud_only_budget():
    data=reports();data['candidate_uncapped']['median_frame_ms']+=.75
    assert not module.validate(data)['passed']
    assert module.validate(data,hud_only=False)['passed']
