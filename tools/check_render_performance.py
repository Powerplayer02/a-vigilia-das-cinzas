"""Release comparison gate for actual 60s native GPU benchmark reports."""
import argparse
import json
from pathlib import Path


def validate(reports, *, hud_only=True):
    problems=[]
    expected=('baseline_capped','candidate_capped','baseline_uncapped','candidate_uncapped')
    for name in expected:
        report=reports[name]
        if (not report.get('valid_sample') or report.get('minimized_frames') != 0
                or not report.get('eligible_fps_baseline') or report.get('qa_diagnostics')
                or report.get('window_type') != 'onscreen'):
            problems.append(name+': invalid, minimized or instrumented sample')
        if (report.get('seconds',0)<60 or report.get('warmup_seconds',0)<5
                or report.get('scenario')!='final_boss_20' or report.get('enemies')!=20
                or report.get('particles_min_max')!=[500,500] or report.get('audio_enabled') is not True
                or report.get('agile_movement_enabled') is not False or report.get('hud')!='full'
                or report.get('resolution')!=[1280,720] or report.get('gc_mode')!='normal'
                or 'profile' in report):
            problems.append(name+': wrong duration or workload')
        if report.get('fps_cap')!=(60 if name.endswith('_capped') else 0):
            problems.append(name+': incorrect frame cap')
        if type(report.get('benchmark_seed')) is not int:
            problems.append(name+': reproducible boss seed missing')
    signatures={json.dumps([r.get('renderer'),r.get('resolution'),r.get('contact_shadow_quality'),
        r.get('audio_enabled'),r.get('agile_movement_enabled'),r.get('benchmark_seed')]) for r in reports.values()}
    if len(signatures)!=1:
        problems.append('Hardware or workload settings differ')
    cap=reports['candidate_capped']
    if cap['median_frame_ms']>16.7 or cap['fps']<59.5:
        problems.append('Candidate does not maintain the capped 60Hz budget')
    base, candidate=reports['baseline_uncapped'],reports['candidate_uncapped']
    delta_median=round(candidate['median_frame_ms']-base['median_frame_ms'],4)
    delta_p95=round(candidate['p95_frame_ms']-base['p95_frame_ms'],4)
    if abs(delta_median)>1 or abs(delta_p95)>1:
        problems.append('Uncapped median/p95 outside +/-1.0ms of baseline')
    if hud_only and delta_median>.5:
        problems.append('HUD-only median overhead exceeds0.5ms')
    return dict(passed=not problems,problems=problems,
        uncapped_delta_median_ms=delta_median,uncapped_delta_p95_ms=delta_p95,
        comparison_scope='hud' if hud_only else 'animation',
        note='Local GPU comparison does not resolve historical stalls or human gameplay difficulty.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('baseline-capped','candidate-capped','baseline-uncapped','candidate-uncapped'):
        parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--animation',action='store_true',help='Use the animation +/-1ms budget; do not apply the HUD-only0.5ms budget')
    args=parser.parse_args()
    reports={key:json.loads(getattr(args,key).read_text()) for key in
        ('baseline_capped','candidate_capped','baseline_uncapped','candidate_uncapped')}
    result=validate(reports,hud_only=not args.animation)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['passed'] else 1)
