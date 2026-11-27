"""Real-clock preboss replay with native PStats and isolated Panda cache.

No HP/damage/position injection. A copied authentic save is controlled through
the same logical commands as play_balance. This investigates rendering, not balance.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]


def child(args):
    sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools')]
    from panda3d.core import ConfigVariableFilename,Filename,load_prc_file_data,PStatCollector,BamCache
    ConfigVariableFilename('model-cache-dir').set_value(Filename.from_os_specific(str(args.cache.resolve())))
    load_prc_file_data('render-diagnostic',f'''want-pstats {str(not args.no_pstats).lower()}
        pstats-host 127.0.0.1
        pstats-port {args.port}
        pstats-tcp-ratio 1
        pstats-max-rate 1000
        pstats-gpu-timing true
        gl-finish {str(args.gl_finish).lower()}
        notify-level-glgsg debug
        notify-timestamp true''')
    import play_balance
    original=play_balance.ArenaApp.start
    def start(app,game):
        original(app,game)
        (args.directory/'runtime.json').write_text(json.dumps(dict(pid=os.getpid(),utc=datetime.now(timezone.utc).isoformat(),
            monotonic=time.monotonic(),clock_mode=int(app._clock.get_mode()),
            cache_root=BamCache.get_global_ptr().get_root().get_fullpath(),
            gpu_timer_supported=app.win.get_gsg().get_supports_timer_query(),
            gpu_timers_active=app.win.get_gsg().get_timer_queries_active()),indent=2))
        if args.trace_native:
            deadline=time.monotonic()+30
            while not (args.directory/'trace-ready').exists():
                if time.monotonic()>deadline: raise RuntimeError('Native tracer did not attach')
                time.sleep(.05)
        clock,playing,phase=(PStatCollector(n) for n in ('QA clock frame','QA playing','QA boss phase'))
        mode=PStatCollector('QA clock mode')
        def marker(task):
            clock.set_level(app._clock.get_frame_count())
            playing.set_level(int(game.flow.simulating))
            phase.set_level(game.boss.phase if game.boss and game.boss.active else 0)
            mode.set_level(int(app._clock.get_mode()))
            return task.cont
        app.taskMgr.add(marker,'native-pstats-correlation',sort=8)
    play_balance.ArenaApp.start=start
    sys.argv=[play_balance.__file__,'--directory',str(args.directory),'--window-type','offscreen']
    play_balance.main()


def run(args):
    directory=args.directory.resolve()
    if directory.exists(): raise ValueError('Use a new directory; old evidence is immutable')
    directory.mkdir(parents=True)
    args.cache.mkdir(parents=True,exist_ok=True)
    cache_before=[p.name for p in args.cache.iterdir()]
    source=args.save.resolve()
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as old:
        with sqlite3.connect(directory/'save.sqlite3') as copied: old.backup(copied)
    (directory/'experiment.json').write_text(json.dumps(dict(source_save_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        cache=str(args.cache.resolve()),cache_entries_before=cache_before,gl_finish=args.gl_finish,
        native_pstats=not args.no_pstats,frida_trace=args.trace_native,
        purpose='Render diagnostic replay, not human balance data',
        driver_cache='NVIDIA driver cache not cleared; only Panda cache is isolated'),indent=2),encoding='utf8')
    native=directory/'native';native.mkdir()
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    server_log=(directory/'native-server.log').open('w')
    native_args=[sys.executable,str(ROOT/'tools/native_pstats.py'),'--directory',str(native),'--port',str(args.port)]
    if args.buffered:native_args.append('--buffered')
    server=None if args.no_pstats else subprocess.Popen(native_args,
        stdout=server_log,stderr=subprocess.STDOUT,creationflags=flags)
    process=None;log=None;trace=None
    try:
        deadline=time.monotonic()+15
        while server is not None and not (native/'ready.json').exists():
            if server.poll() is not None or time.monotonic()>deadline: raise RuntimeError('Native server did not become ready')
            time.sleep(.05)
        command=[sys.executable,str(Path(__file__).resolve()),'--child','--directory',str(directory),
            '--cache',str(args.cache.resolve()),'--port',str(args.port)]
        if args.gl_finish: command.append('--gl-finish')
        if args.no_pstats: command.append('--no-pstats')
        if args.trace_native: command.append('--trace-native')
        log=(directory/'driver.log').open('w')
        process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,creationflags=flags)
        if args.trace_native:
            from native_trace import NativeTrace
            deadline=time.monotonic()+35
            while not (directory/'runtime.json').exists():
                if process.poll() is not None or time.monotonic()>deadline: raise RuntimeError('Replay did not reach native trace gate')
                time.sleep(.05)
            runtime=json.loads((directory/'runtime.json').read_text())
            trace=NativeTrace(runtime['pid'],directory)
            (directory/'trace-ready').touch()
        def send(steps,*,pause=True,quit=False):
            deadline=time.monotonic()+30
            while not (directory/'commands').exists():
                if process.poll() is not None or time.monotonic()>deadline: raise RuntimeError('Driver failed during startup')
                time.sleep(.05)
            identity=str(time.time_ns())+'-'+uuid.uuid4().hex[:6]
            path=directory/'commands'/(identity+'.json');tmp=path.with_suffix('.tmp')
            tmp.write_text(json.dumps(dict(id=identity,steps=steps,pause_after=pause,quit=quit,
                note='Native PStats/cache/glFinish render investigation, not balance certification')))
            tmp.replace(path)
            if quit:return None
            deadline=time.monotonic()+sum(s.get('seconds',s.get('encounter_seconds',0)) for s in steps)+35
            response=directory/'observations'/(identity+'.json')
            while not response.exists():
                if process.poll() is not None or time.monotonic()>deadline: raise RuntimeError('Input observation timed out')
                time.sleep(.05)
            return json.loads(response.read_text(encoding='utf8'))
        original=ROOT/'artifacts/balance/custodian_tempo_final/commands'
        for name in ('1795788476592851900-8103a9a7.json','1795788477911363100-60b7eb3e.json'):
            response=send(json.loads((original/name).read_text())['steps'])
            print(json.dumps(dict(stage='route',active_s=response['active_s'],area=response['area'])),flush=True)
        for index in range(args.blocks):
            steps=[dict(keys=['escape'],seconds=.04),dict(keys=[],seconds=.04)]
            steps += [dict(encounter_seconds=20) for _ in range(3)]
            response=send(steps)
            if trace: trace.checkpoint()
            print(json.dumps(dict(stage='render-replay',block=index+1,active_s=response['active_s'],
                area=response['area'],state=response['state'])),flush=True)
        if trace: trace.checkpoint();trace.close();trace=None
        send([],quit=True);process.wait(timeout=20)
        if process.returncode: raise RuntimeError('Replay failed; inspect driver.log')
    finally:
        if trace:trace.close()
        if process is not None and process.poll() is None:
            try:
                target=directory/'commands'/'stop-diagnostic.json'
                target.write_text(json.dumps(dict(id='stop-diagnostic',steps=[],quit=True)))
                process.wait(timeout=10)
            except Exception: process.terminate();process.wait(timeout=10)
        (native/'stop').touch()
        if server is not None:server.wait(timeout=120)
        server_log.close()
        if log:log.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--cache',type=Path,required=True)
    p.add_argument('--save',type=Path)
    p.add_argument('--gl-finish',action='store_true')
    p.add_argument('--buffered',action='store_true')
    p.add_argument('--trace-native',action='store_true',help='Optional Frida native call timings; diagnostic overhead applies')
    p.add_argument('--no-pstats',action='store_true',help='Control run without a native PStats connection')
    p.add_argument('--blocks',type=int,choices=range(1,5),default=4)
    p.add_argument('--port',type=int,default=62185)
    p.add_argument('--child',action='store_true',help=argparse.SUPPRESS)
    args=p.parse_args()
    if args.child:child(args)
    else:
        if args.save is None:p.error('--save is required')
        run(args)
