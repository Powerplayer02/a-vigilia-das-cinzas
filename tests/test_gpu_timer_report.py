"""GPU query diagnostics separate startup and never qualify as FPS acceptance."""
import gzip
from importlib.util import module_from_spec,spec_from_file_location
import json
from pathlib import Path

spec=spec_from_file_location('gpu_timers',Path(__file__).parents[1]/'tools/diagnose_gpu_timers.py')
module=module_from_spec(spec);spec.loader.exec_module(module)


def test_only_exact_measured_frame_ids_enter_gpu_measurement_summary(tmp_path):
    (tmp_path/'native').mkdir()
    (tmp_path/'benchmark.json').write_text(json.dumps(dict(renderer='fixtureGPU',
        gpu_timer_supported=True,gpu_timer_queries_active=True)))
    rows=[dict(thread='Main',frame=1,levels={'QA measuring':0}),
        dict(thread='Main',frame=2,levels={'QA measuring':1}),
        dict(thread='fixtureGPU',frame=1,frame_ms=300,root_bars_ms={'Draw':299}),
        dict(thread='fixtureGPU',frame=2,frame_ms=1.4,root_bars_ms={'Draw':1.2})]
    with gzip.open(tmp_path/'native/native-frames.jsonl.gz','wt') as stream:
        stream.write('\n'.join(json.dumps(row) for row in rows))
    report=module.summarize(tmp_path)
    assert report['available'] and not report['eligible_fps_baseline']
    assert report['gpu_entire_session']['max_ms']==300
    assert report['gpu_exact_frame_id_matches_during_measurement']['max_ms']==1.4
    assert report['measured_draw']['max_ms']==1.2
