"""30s direct-counter checkpoint before adding the particle layer."""
import argparse
import json
import math
from pathlib import Path


def validate(report):
    problems=[];notes=[]
    if (not report.get('eligible_fps_baseline') or not report.get('valid_sample')
        or report.get('minimized_frames')!=0 or report.get('window_type')!='onscreen'
        or report.get('unfocused_frames',0)!=0
        or report.get('seconds',0)<30 or report.get('warmup_seconds',0)<5
        or report.get('fps_cap')!=60 or report.get('pstats_connected')
        or report.get('gl_finish') or report.get('qa_diagnostics') or 'profile' in report):
        problems.append('Invalid duration, window, cap or instrumentation')
    if (report.get('scenario')!='final_boss_20' or report.get('enemies')!=20
        or report.get('boss_phase')!=3 or report.get('particles_min_max')!=[500,500]
        or report.get('audio_enabled') is not True):problems.append('Wrong stress workload')
    timing=report.get('animation_timing',{})
    inclusive='animation_inclusive_median_ms_per_render' in timing
    prefix='animation_inclusive' if inclusive else 'animation_total'
    values=[report.get('median_frame_ms'),timing.get(prefix+'_median_ms_per_render'),
        timing.get(prefix+'_p95_ms_per_render')]
    if any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in values):
        problems.append('Missing or invalid direct timing')
    else:
        frame,median,p95=values
        if frame>16.7:problems.append('Capped frame median exceeds16.7ms')
        if median>4 or p95>4:problems.append('Animation median or p95 exceeds4ms')
        elif median>2:notes.append('Animation median between2 and4ms; accepted with note per revised protocol')
    if (not report.get('animation_direct_timing') or timing.get('render_frames',0)<1
        or timing.get('render_frames')!=report.get('frames')
        or not timing.get('direct_scopes',{}).get('fixed_step',{}).get('calls')):
        problems.append('Direct animation/fixed-step counters missing or incomplete')
    return dict(passed=not problems,problems=problems,notes=notes,
        scope='Phase4 direct CPU/capped checkpoint only; uncapped and120s spikes remain for phase5')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=validate(json.loads(args.report.read_text(encoding='utf8')))
    args.output.write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps(result,indent=2));raise SystemExit(0 if result['passed'] else 1)
