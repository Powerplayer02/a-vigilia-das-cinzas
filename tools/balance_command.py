"""Send bounded, real-time input to a play_balance session and await its rendered observation."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import uuid

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--directory',type=Path,default=Path('artifacts/balance/off_agent_01'))
parser.add_argument('--keys',nargs='*',default=[])
parser.add_argument('--tap',nargs='*',default=[])
parser.add_argument('--repeat',type=int,default=1)
parser.add_argument('--interval',type=float,default=.25)
parser.add_argument('--seconds',type=float,default=0)
parser.add_argument('--settle',type=float,default=0)
parser.add_argument('--encounter-seconds',type=float,default=0)
parser.add_argument('--look',nargs=2,type=float)
parser.add_argument('--pause',action='store_true')
parser.add_argument('--resume-first',action='store_true')
parser.add_argument('--note')
parser.add_argument('--quit',action='store_true')
parser.add_argument('--plan',type=Path,help='Explicit normal-key steps, each at most 20 real seconds')
args=parser.parse_args()
assert 0<=args.seconds<=20 and 0<=args.settle<=20 and 0<=args.encounter_seconds<=20 and 1<=args.repeat<=30 and .12<=args.interval<=3
identity=str(time.time_ns())+'-'+uuid.uuid4().hex[:8]
steps=[]
if args.resume_first:steps.extend((dict(keys=['escape'],seconds=.04),dict(keys=[],seconds=.04)))
if args.plan:
    planned=json.loads(args.plan.read_text(encoding='utf-8-sig'))
    assert isinstance(planned,list) and len(planned)<=50
    assert all(isinstance(step,dict) and 0<float(step.get('seconds',0))<=20 for step in planned)
    steps.extend(planned)
if args.look:steps.append(dict(keys=args.keys,look=args.look,seconds=.1))
for _ in range(args.repeat):
    for key in args.tap:
        steps.extend((dict(keys=[*args.keys,key],seconds=.07),dict(keys=args.keys,seconds=max(.05,args.interval-.07))))
if args.seconds:steps.append(dict(keys=args.keys,seconds=args.seconds))
if args.settle:steps.append(dict(keys=[],seconds=args.settle))
if args.encounter_seconds:steps.append(dict(encounter_seconds=args.encounter_seconds))
command=dict(id=identity,steps=steps,pause_after=args.pause,note=args.note,quit=args.quit)
directory=args.directory.resolve();path=directory/'commands'/(identity+'.json')
if args.encounter_seconds:
    policy=Path(__file__).with_name('balance_actions.py').read_bytes()
    archive=directory/'policies';archive.mkdir(exist_ok=True)
    policy_path=archive/(hashlib.sha256(policy).hexdigest()+'.py')
    if not policy_path.exists():policy_path.write_bytes(policy)
temp=path.with_suffix('.tmp');temp.write_text(json.dumps(command),encoding='utf8');temp.replace(path)
response=directory/'observations'/(identity+'.json');deadline=time.monotonic()+sum(step.get('seconds',step.get('encounter_seconds',0)) for step in steps)+20
if args.quit:print(json.dumps({'queued':identity,'quit':True}));raise SystemExit()
while not response.exists():
    if time.monotonic()>deadline:raise TimeoutError('Input observation timed out; inspect session log before retrying')
    time.sleep(.05)
print(json.dumps(json.loads(response.read_text(encoding='utf8')),ensure_ascii=True))
