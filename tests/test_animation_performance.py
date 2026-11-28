"""Performance acceptance must reject incomplete or contaminated coverage."""
import copy
from importlib.util import module_from_spec,spec_from_file_location
from pathlib import Path

import pytest
from vigilia.engine.animation import WARMUP_CLIPS
from vigilia.model.enemies import ENEMIES

spec=spec_from_file_location('animation_gate',Path(__file__).parents[1]/'tools/check_animation_performance.py')
gate=module_from_spec(spec);spec.loader.exec_module(gate)


def reports():
    common=dict(eligible_fps_baseline=True,valid_sample=True,minimized_frames=0,
        window_type='onscreen',seconds=120,warmup_seconds=5,qa_diagnostics=False,
        pstats_connected=False,gl_finish=False,scenario='final_boss_20',enemies=20,
        particles_min_max=[500,500],audio_enabled=True,fps_cap=0,median_frame_ms=3.665,p95_frame_ms=7.0191,max_frame_ms=32,frames=1000)
    capped=dict(common,fps_cap=60,median_frame_ms=16.666)
    coverage=copy.deepcopy(common)
    coverage['animation_workload']=dict(seen={role:list(WARMUP_CLIPS) for role in ('player',*ENEMIES)})
    coverage['enemy_profile_ids']=list(ENEMIES)
    coverage['animation_direct_timing']=True
    coverage['animation_timing']=dict(render_frames=1000,animation_total_mean_ms_per_render=.7)
    coverage['animation_workload']['seen']['boss:fixture']=[f'{phase}:{clip}' for phase in (1,2,3) for clip in WARMUP_CLIPS]
    return capped,common,coverage


def test_complete_native_coverage_can_pass():
    assert gate.validate(*reports())['passed']


@pytest.mark.parametrize('field,value',(('minimized_frames',1),('unfocused_frames',1),('pstats_connected',True),('gl_finish',True),('seconds',119)))
def test_contaminated_or_short_coverage_cannot_pass(field,value):
    capped,uncapped,coverage=reports();coverage[field]=value
    assert not gate.validate(capped,uncapped,coverage)['passed']


def test_a_missing_boss_phase_pose_and_a_51ms_frame_both_fail():
    capped,uncapped,coverage=reports();coverage['animation_workload']['seen']['boss:fixture'].pop()
    coverage['max_frame_ms']=51
    assert len(gate.validate(capped,uncapped,coverage)['problems'])==2


def test_three_families_or_missing_animation_cpu_cost_cannot_pass():
    capped,uncapped,coverage=reports()
    for role in list(ENEMIES)[3:]:del coverage['animation_workload']['seen'][role]
    coverage['animation_timing']['animation_total_mean_ms_per_render']=3.1
    assert not gate.validate(capped,uncapped,coverage)['passed']


def test_animation_cpu_nan_or_an_incomplete_measurement_cannot_pass():
    for value,frames in ((float('nan'),1000),(.3,1)):
        capped,uncapped,coverage=reports()
        coverage['animation_timing'].update(animation_total_mean_ms_per_render=value,render_frames=frames)
        assert not gate.validate(capped,uncapped,coverage)['passed']


def test_particle_layer_requires_the_real_ceiling_and_separate_particle_cpu_counter():
    capped,uncapped,coverage=reports()
    coverage.update(particles_min_max=[2000,2000],particle_pool_capacity=2000,particle_admission_limit=2000)
    coverage['animation_timing'].update(animation_total_median_ms_per_render=.8,
        animation_total_p95_ms_per_render=1.7,direct_scopes={'particles':{'calls':1000}})
    assert gate.validate(capped,uncapped,coverage,particle_layer=True)['passed']
    coverage['particle_pool_capacity']=5000
    assert not gate.validate(capped,uncapped,coverage,particle_layer=True)['passed']
