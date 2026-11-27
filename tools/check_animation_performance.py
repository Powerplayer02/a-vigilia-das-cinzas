"""Phase4 GPU gate: comparable controls plus explicit 120s catalog coverage."""
import argparse
import json
import math
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from vigilia.engine.animation import WARMUP_CLIPS
from vigilia.model.enemies import ENEMIES


def validate(capped,uncapped,coverage):
    problems=[]
    for name,report,duration in (('capped',capped,60),('uncapped',uncapped,60),('coverage',coverage,120)):
        if (not report.get('eligible_fps_baseline') or not report.get('valid_sample') or report.get('minimized_frames')!=0
            or report.get('window_type')!='onscreen' or report.get('seconds',0)<duration
            or report.get('warmup_seconds',0)<5 or report.get('qa_diagnostics') or report.get('pstats_connected')
            or report.get('gl_finish') or 'profile' in report):problems.append(name+': invalid duration, window or instrumentation')
        if (report.get('scenario')!='final_boss_20' or report.get('enemies')!=20
            or report.get('particles_min_max')!=[500,500] or report.get('audio_enabled') is not True):
            problems.append(name+': wrong stress workload')
    if capped.get('fps_cap')!=60 or capped.get('median_frame_ms',100)>16.7:problems.append('capped: exceeds16.7ms median')
    if uncapped.get('fps_cap')!=0:problems.append('uncapped: must have no cap')
    if abs(uncapped.get('median_frame_ms',100)-3.665)>1 or abs(uncapped.get('p95_frame_ms',100)-7.0191)>1:
        problems.append('uncapped: median/p95 outside +/-1ms of accepted baseline')
    if coverage.get('max_frame_ms',100)>50:problems.append('coverage: frame above50ms')
    workload=coverage.get('animation_workload',{})
    seen=workload.get('seen',{})
    expected=set(WARMUP_CLIPS)
    if set(seen.get('player',[]))!=expected:problems.append('coverage: missing player clips')
    common=[role for role in seen if role!='player' and not role.startswith('boss:')]
    if set(common)!=set(ENEMIES) or any(set(seen[role])!=expected for role in common):problems.append('coverage: missing enemy families or clips')
    if set(coverage.get('enemy_profile_ids',[]))!=set(ENEMIES):problems.append('coverage: actual world does not contain all six families')
    bosses=[role for role in seen if role.startswith('boss:')]
    if not bosses or any(set(seen[role])!={f'{phase}:{clip}' for phase in (1,2,3) for clip in expected} for role in bosses):
        problems.append('coverage: missing boss phase/clip pairs')
    timing=coverage.get('animation_timing',{})
    mean=timing.get('animation_total_mean_ms_per_render')
    if (not coverage.get('animation_direct_timing') or timing.get('render_frames',0)<1
            or timing.get('render_frames')!=coverage.get('frames')
            or type(mean) not in (int,float) or not math.isfinite(mean) or mean>2):
        problems.append('coverage: animation CPU timing missing or above2ms per render')
    return dict(passed=not problems,problems=problems,
        note='Catalog-pose stress over production combat, not proof that each action was played through inputs. Historical stall remains open.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('capped','uncapped','coverage','output'):parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args()
    result=validate(*(json.loads(getattr(args,name).read_text(encoding='utf8')) for name in ('capped','uncapped','coverage')))
    args.output.write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps(result,indent=2));raise SystemExit(0 if result['passed'] else 1)
