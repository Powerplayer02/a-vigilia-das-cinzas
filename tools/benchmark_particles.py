"""Particle update wall-time diagnostic without a window/GPU; not an FPS gate."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from panda3d.core import NodePath
from vigilia.core.mathx import Vec3
from vigilia.engine.particles import ParticleEmitter


def measure(capacity,count,steps=1500):
    emitter=ParticleEmitter(NodePath('diagnostic'),capacity=capacity)
    target=Vec3(240,25,1)
    emitter.spawn('embers',target,count=count)
    samples=[]
    for index in range(steps+200):
        start=time.perf_counter()
        emitter.update(1/120,target)
        missing=count-emitter.pool.active_count
        if missing:emitter.spawn('embers',target,count=missing)
        if index>=200:samples.append((time.perf_counter()-start)*1000)
    ordered=sorted(samples)
    return dict(capacity=capacity,active=count,steps=steps,
        median_ms=statistics.median(ordered),p95_ms=ordered[math.ceil(.95*len(ordered))-1])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=dict(kind=__doc__,source_sha256=hashlib.sha256((ROOT/'src/vigilia/engine/particles.py').read_bytes()).hexdigest(),
        rows=[measure(500,500),measure(2000,500),measure(2000,2000)])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print(json.dumps(result,indent=2))
