"""Separate native timer-query diagnostic. Never a frame-time acceptance run."""
import argparse
import gzip
import json
import math
from pathlib import Path
import socket
import statistics
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]


def distribution(values):
    ordered=sorted(values)
    if not ordered:return dict(frames=0,median_ms=None,p95_ms=None,max_ms=None)
    return dict(frames=len(ordered),median_ms=statistics.median(ordered),
        p95_ms=ordered[math.ceil(len(ordered)*.95)-1],max_ms=max(ordered))


def summarize(directory):
    benchmark=json.loads((directory/'benchmark.json').read_text(encoding='utf8'))
    rows=[];measuring=set()
    with gzip.open(directory/'native/native-frames.jsonl.gz','rt',encoding='utf8') as stream:
        for line in stream:
            row=json.loads(line)
            if row['thread']=='Main' and row['levels'].get('QA measuring')==1:measuring.add(row['frame'])
            if row['thread']==benchmark['renderer']:rows.append(row)
    captured=[row for row in rows if row['frame'] in measuring]
    supported=benchmark.get('gpu_timer_supported',False)
    active=benchmark.get('gpu_timer_queries_active',False)
    summary=dict(instrument='Panda native GPU timer queries, gl-finish OFF; PStats transport remains instrumented',
        eligible_fps_baseline=False,gpu_timer_supported=supported,gpu_timer_queries_active=active,
        source_build_id=benchmark.get('source_build_id'),renderer=benchmark['renderer'],
        gpu_entire_session=distribution([r['frame_ms'] for r in rows]),
        gpu_exact_frame_id_matches_during_measurement=distribution([r['frame_ms'] for r in captured]),
        measured_draw=distribution([r['root_bars_ms']['Draw'] for r in captured if 'Draw' in r['root_bars_ms']]),
        unmatched_gpu_frames=len(rows)-len(captured),
        limitations=['Native collector delivery gaps are retained in native-summary.json.',
            'GPU frame IDs matched exactly with Main QA measuring markers; unmatched rows are excluded from measurement-only figures.',
            'Timer queries avoid forced glFinish synchronization, not all profiler overhead or scheduling effects.',
            'No result from this run can replace uninstrumented FPS acceptance.'])
    summary['available']=bool(supported and active and captured)
    (directory/'gpu-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
    return summary


def run(directory,seconds,particles=500):
    directory=directory.resolve()
    if directory.exists():raise ValueError('Use a new directory; diagnostic evidence is immutable')
    directory.mkdir(parents=True)
    with socket.socket() as port_probe:
        port_probe.bind(('127.0.0.1',0));port=port_probe.getsockname()[1]
    native=directory/'native';native.mkdir()
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    with (directory/'server.log').open('w') as server_log:
        server=subprocess.Popen([sys.executable,str(ROOT/'tools/native_pstats.py'),
            '--directory',str(native),'--port',str(port),'--buffered'],stdout=server_log,
            stderr=subprocess.STDOUT,creationflags=flags)
        process=None
        try:
            deadline=time.monotonic()+15
            while not (native/'ready.json').exists():
                if server.poll() is not None or time.monotonic()>deadline:raise RuntimeError('Native server not ready')
                time.sleep(.05)
            with (directory/'benchmark.log').open('w') as log:
                process=subprocess.Popen([sys.executable,str(ROOT/'tools/benchmark.py'),'--seconds',str(seconds),
                    '--warmup-seconds','5','--final-boss','--enemies','20','--all-enemy-profiles',
                    '--particles',str(particles),'--procedural-music','--procedural-sfx','--pstats-port',str(port),
                    '--pstats-max-rate','60','--output',str(directory/'benchmark.json')],
                    stdout=log,stderr=subprocess.STDOUT,creationflags=flags,cwd=ROOT)
                if process.wait(timeout=seconds+120):raise RuntimeError('GPU diagnostic failed; inspect benchmark.log')
        finally:
            if process is not None and process.poll() is None:process.terminate();process.wait(timeout=10)
            (native/'stop').touch()
            server.wait(timeout=120)
    result=summarize(directory)
    if not result['available']:raise RuntimeError('Timer-query diagnostic unavailable; no glFinish fallback was applied')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--seconds',type=int,default=10)
    parser.add_argument('--particles',type=int,choices=(500,2000),default=500)
    args=parser.parse_args()
    if args.seconds<1:parser.error('--seconds must be positive')
    run(args.directory,args.seconds,args.particles)
