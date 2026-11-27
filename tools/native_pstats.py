"""Capture native Panda1.10 text-stats events; this is NOT CPython pstats.

The official text-stats server decodes the protocol. This adapter retains its
native events and hierarchical, inclusive timings in a compressed JSON stream.
Reference: panda3d/v1.10.16/pandatool/src/text-stats/textMonitor.cxx.
"""
import argparse
from collections import defaultdict, deque
import gzip
import json
import math
from pathlib import Path
import re
import subprocess
import threading
import time

HEADER=re.compile(r'^\s*Thread (.+?) frame (\d+), ([\d.eE+-]+) ms')
EVENT=re.compile(r'^\s*([\d.eE+-]+)\s+(start|stop)\s+(.+?)\s*$')
VALUE=re.compile(r'^( +)(.+?) = ([\d.eE+-]+)\s*(.*?)\s*$')


class NativeParser:
    def __init__(self):
        self.current=None
        self.stack=[]

    def feed(self,line):
        header=HEADER.match(line)
        if header:
            previous=self.finish()
            self.current=dict(thread=header[1],frame=int(header[2]),frame_ms=float(header[3]),
                events=[],timings=[],levels={})
            return previous
        if self.current is None: return None
        event=EVENT.match(line)
        if event:
            self.current['events'].append([float(event[1]),event[2],event[3]])
            return None
        value=VALUE.match(line)
        if value:
            indent,name,number,units=len(value[1]),value[2],float(value[3]),value[4]
            if units=='ms':
                while self.stack and self.stack[-1][0]>=indent: self.stack.pop()
                path=[name for _,name in self.stack]+[name]
                self.current['timings'].append(dict(path=':'.join(path),inclusive_ms=number))
                self.stack.append((indent,name))
            elif name.startswith('QA '):
                self.current['levels'][name]=number
        return None

    def finish(self):
        row,self.current=self.current,None
        self.stack=[]
        if row is None: return None
        # TextMonitor prints get_net_value(): already includes descendants.
        row['inclusive_ms']={entry['path']:entry['inclusive_ms'] for entry in row['timings']}
        row['root_bars_ms']={k:v for k,v in row['inclusive_ms'].items() if ':' not in k}
        return row


def capture(directory,port,buffered=False):
    import panda3d_tools
    directory=directory.resolve();directory.mkdir(parents=True,exist_ok=True)
    binary=Path(panda3d_tools.__file__).parent/'text-stats.exe'
    if not binary.exists(): binary=binary.with_suffix('')
    args=[str(binary),'-p',str(port),'-r']
    server_log=None
    if buffered:
        # std::ofstream is buffered. The native default nout/stderr flushes on
        # each insertion and can overwhelm its own observer at high frame rates.
        args+=['-o','native-text.log']
        server_log=(directory/'server-process.log').open('wb')
    process=subprocess.Popen(args,stdout=server_log if buffered else subprocess.PIPE,
        stderr=subprocess.STDOUT,cwd=directory,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    stop=threading.Event()
    def watch():
        while not stop.wait(.1):
            if (directory/'stop').exists():
                process.terminate();return
    watcher=threading.Thread(target=watch,daemon=True);watcher.start()
    def source():
        if not buffered:
            yield from process.stdout
            return
        path=directory/'native-text.log'
        while not path.exists():
            if process.poll() is not None: return
            time.sleep(.01)
        (directory/'ready.json').write_text(json.dumps(dict(port=port,pid=process.pid)))
        with path.open('rb') as stream:
            pending=b''
            while True:
                line=stream.readline()
                if line:
                    pending+=line
                    if pending.endswith(b'\n'):
                        yield pending;pending=b''
                elif process.poll() is not None:
                    if pending:yield pending
                    return
                else:time.sleep(.01)
    parser=NativeParser();durations=defaultdict(list);rings=defaultdict(lambda:deque(maxlen=31))
    worst={};playing_worst={};gaps=defaultdict(int);last={};captures=[]
    def retain(row,stream):
        if row is None or not math.isfinite(row['frame_ms']): return
        name=row['thread'];durations[name].append(row['frame_ms'])
        if name in last: gaps[name]+=max(0,row['frame']-last[name]-1)
        last[name]=row['frame'];rings[name].append(row)
        if name not in worst or row['frame_ms']>worst[name]['frame_ms']: worst[name]=row
        if row['levels'].get('QA playing')==1 and row['levels'].get('QA boss phase',0)>0:
            if name not in playing_worst or row['frame_ms']>playing_worst[name]['frame_ms']:
                playing_worst[name]=row
            if row['frame_ms']>=200:
                captures.append(dict(thread=name,frame=row['frame'],previous=list(rings[name])))
                captures.sort(key=lambda x:x['previous'][-1]['frame_ms'],reverse=True)
                del captures[8:]
        stream.write(json.dumps(row,separators=(',',':'))+'\n')
    try:
        with gzip.open(directory/'native-frames.jsonl.gz','wt',encoding='utf8',compresslevel=1) as stream:
            for raw in source():
                line=raw.decode('utf8',errors='replace').strip('\r\n')
                if 'Listening for connections' in line:
                    (directory/'ready.json').write_text(json.dumps(dict(port=port,pid=process.pid)))
                retain(parser.feed(line),stream)
            retain(parser.finish(),stream)
    finally:
        stop.set()
        if process.poll() is None: process.terminate()
        process.wait(timeout=10);watcher.join(timeout=2)
        if server_log:server_log.close()
        summaries={}
        for name,values in durations.items():
            ordered=sorted(values)
            summaries[name]=dict(frames=len(values),missing_frame_ids=gaps[name],
                median_ms=ordered[len(ordered)//2],p95_ms=ordered[math.ceil(len(ordered)*.95)-1],
                worst=worst[name],worst_gameplay=playing_worst.get(name))
        (directory/'native-summary.json').write_text(json.dumps(dict(
            format='Native Panda3D1.10 text-stats -r, not CPython cProfile',buffered_native_output=buffered,threads=summaries,
            slow_captures=captures,limitations=['Native frame gaps are counted; original CPython capture cannot be reconstructed as native data.']),indent=2),encoding='utf8')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--port',type=int,required=True)
    p.add_argument('--buffered',action='store_true')
    args=p.parse_args();capture(args.directory,args.port,args.buffered)
