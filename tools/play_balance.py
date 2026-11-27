"""Real-time, production-rules balance session driven through Game.keyboard.

Only the outer input adapter differs from main.py: logical key holds also work
while the desktop app is in the background. No gameplay state is injected.
"""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from panda3d.core import Filename,PNMImage,TextNode
from vigilia.core.config import load_config
from vigilia.core.events import (AreaEnteredEvent,BonfireRestedEvent,BossArenaEnteredEvent,
    BossDefeatedEvent,ItemUseStartedEvent,LevelUpEvent,EndingChosenEvent,AppStateChangedEvent)
from vigilia.combat.events import DamageDealt,EntityDied,ParrySucceeded,HPChangedEvent,HealingApplied,StaggerTriggered
from vigilia.core.types import GameState
from vigilia.core.mathx import Transform
from vigilia.engine.app import ArenaApp
from vigilia.engine.diagnostics import build_fingerprint
from vigilia.game import Game
import balance_actions


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,default=ROOT/'artifacts/balance/off_agent_01')
    parser.add_argument('--resume',action='store_true')
    parser.add_argument('--window-type',choices=('onscreen','offscreen'),default='onscreen')
    args=parser.parse_args();directory=args.directory.resolve();directory.mkdir(parents=True,exist_ok=True)
    inbox=directory/'commands';inbox.mkdir(exist_ok=True)
    output=directory/'observations';output.mkdir(exist_ok=True)
    if (directory/'session.json').exists() and not args.resume:
        raise RuntimeError('Use a new session directory; existing evidence is immutable')
    config=load_config(ROOT/'data/config.toml')
    assert not config.ultrakill_style
    tables={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
        for d in ('data/bosses','data/enemies','data/classes') for p in (ROOT/d).glob('*.toml')}
    metadata=dict(client_date='2026-11-27',started_utc=datetime.now(timezone.utc).isoformat(),
        commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),
        source_build_id=build_fingerprint(ROOT),driver='Agent chooses logical keyboard/mouse input; real clock',
        production_tables=tables,agile_movement=False,fast_forward=False,window_type=args.window_type,
        pauses='Normal Escape/menu pauses are logged; active time excludes menus',
        manual_human_playthrough=False,
        observation='Rendered image plus own pose/action/resources and locked-target range; no AI state')
    if args.resume:
        previous=json.loads((directory/'session.json').read_text(encoding='utf8'))
        assert previous['production_tables']==tables and previous['source_build_id']==metadata['source_build_id']
    else:(directory/'session.json').write_text(json.dumps(metadata,indent=2),encoding='utf8')
    app=ArenaApp(config,window_type=args.window_type)
    app.ignore('vigilia-button-down');app.ignore('vigilia-button-up')
    work=queue.Queue()
    def writer():
        with (directory/'events.jsonl').open('a',encoding='utf8',buffering=1) as stream:
            while True:
                item=work.get()
                if item is None:work.task_done();break
                kind,payload=item
                try:
                    if kind=='event':stream.write(json.dumps(payload,ensure_ascii=False)+'\n')
                    else:
                        image,response=payload
                        path=output/(response['id']+'.png')
                        assert image.write(Filename.from_os_specific(str(path)))
                        response['screenshot']=str(path)
                        temp=output/(response['id']+'.tmp')
                        temp.write_text(json.dumps(response,ensure_ascii=False,indent=2),encoding='utf8')
                        temp.replace(output/(response['id']+'.json'))
                except Exception as exc:
                    (directory/'writer-error.txt').write_text(repr(exc),encoding='utf8')
                finally:work.task_done()
    worker=threading.Thread(target=writer,name='balance-evidence',daemon=True);worker.start()
    try:
        game=Game(app,config,ROOT/'assets',save_path=directory/'save.sqlite3',
            settings_path=directory/'options.toml',front_end=True,enemy_count=3)
        app.start(game);app.taskMgr.remove('vigilia-update')
        app.graphicsEngine.render_frame();app.graphicsEngine.render_frame()
        monitor=game.enable_diagnostics(directory/'spikes',report_path=directory/'diagnostics.json')
        old_events=[json.loads(line) for line in (directory/'events.jsonl').read_text(encoding='utf8').splitlines()] if args.resume else []
        active=old_events[-1]['active_s'] if old_events else 0.
        wall_offset=old_events[-1]['wall_s'] if old_events else 0.
        started=time.monotonic();sequence=[];held=set();command=None
        due=0.;look=(0.,0.);capture=[]
        policy=None;policy_until=0.
        seen={p.name for p in inbox.glob('*.json')} if args.resume else set()
        last_sample=active
        next_poll=0.
        def log(kind,data):
            work.put(('event',dict(type=kind,active_s=round(active,6),wall_s=round(time.monotonic()-started+wall_offset,6),
                area=game.active_area,**data)))
        def event(value):
            keys=game._actor_keys();keys[game._entity.id]='player'
            data=asdict(value)
            for field in ('source','target','entity_id','attacker','defender'):
                if isinstance(data.get(field),int):data[field+'_key']=keys.get(data[field],f'actor:{data[field]}')
            data['boss_phase']=game.boss.phase if game.boss else None
            log(type(value).__name__,data)
        for kind in (AreaEnteredEvent,BonfireRestedEvent,BossArenaEnteredEvent,BossDefeatedEvent,
            ItemUseStartedEvent,LevelUpEvent,EndingChosenEvent,AppStateChangedEvent,DamageDealt,
            EntityDied,ParrySucceeded,HPChangedEvent,HealingApplied,StaggerTriggered):game._bus.subscribe(kind,event)
        log('SessionContinued' if args.resume else 'SessionStarted',metadata)
        def visible_text():
            return [node.node().get_text() for node in app.aspect2d.find_all_matches('**/+TextNode')
                if not node.is_hidden() and node.node().get_text().strip()]
        def telemetry():
            forward,_=game._camera.axes(game._transform.position)
            target=game._target
            target_pose=game._world.get(target,Transform) if target is not None else None
            attack=game._fighter.attack
            return dict(player_position=asdict(game._transform.position),
                camera_forward=asdict(forward),player_yaw=game._transform.yaw,
                hp=game._fighter.hp,stamina=game._fighter.stamina,
                own_action=game._commands.state.value,
                own_action_remaining_steps=(max(0,attack.definition.duration-attack.age) if attack else 0),
                target=(dict(key=game._actor_keys().get(target.id,str(target.id)),
                    position=asdict(target_pose.position),
                    distance=(target_pose.position-game._transform.position).flat().length())
                    if target_pose is not None else None),
                rendered_aoe_radius=(game._renderer._boss_ring.get_sx()
                    if not game._renderer._boss_ring.is_hidden() else 0.))
        def set_keys(keys):
            nonlocal held
            keys=set(keys)
            if keys & {'f5','f7','f8','f9'}:raise ValueError('Debug reset/load keys are disabled for this session')
            if policy is not None and keys != held:
                log('AgentSequenceKeys',dict(keys=sorted(keys)))
            for key in sorted(held-keys):game.keyboard(key,False)
            for key in sorted(keys-held):game.keyboard(key,True)
            held=keys
        def update(task):
            nonlocal active,sequence,command,due,look,last_sample,policy,policy_until,next_poll
            now=time.monotonic()
            if command is None and now >= next_poll:
                next_poll=now+.1
                with os.scandir(inbox) as entries:
                    pending=sorted(entry.name for entry in entries
                        if entry.name.endswith('.json') and entry.name not in seen)
                if pending:
                    path=inbox/pending[0];seen.add(path.name);command=json.loads(path.read_text(encoding='utf8'))
                    log('AgentCommand',command)
                    if command.get('quit'):
                        set_keys([]);game.request_quit();return task.done
                    if command.get('note'):log('AgentNote',{'note':command['note']})
                    sequence=list(command.get('steps',[]));due=now
            if policy is not None:
                if (now < policy_until and game._fighter.hp > 0 and game._target is not None
                        and app.state == GameState.PLAYING and game.flow.simulating):
                    set_keys(policy.choose(game,now))
                else:
                    policy=None;due=now;set_keys([])
            if command is not None and policy is None and now>=due:
                if sequence:
                    step=sequence.pop(0)
                    if 'encounter_seconds' in step:
                        policy=importlib.reload(balance_actions).EncounterInputs()
                        policy_until=now+max(.1,min(20,float(step['encounter_seconds'])))
                        log('AgentInputSequence',dict(seconds=policy_until-now,
                            reaction_seconds=policy.reaction_seconds,
                            policy_sha256=hashlib.sha256((ROOT/'tools/balance_actions.py').read_bytes()).hexdigest(),
                            perception='rendered AoE circle/color, own state, locked-target pose and static scene collision; no enemy AI state'))
                    else:
                        set_keys(step.get('keys',[]));look=tuple(step.get('look',(0,0)))
                        due=now+max(.04,min(20,float(step.get('seconds',.1))))
                else:
                    set_keys([])
                    frozen=None
                    if command.get('pause_after') and app.state==GameState.PLAYING and game.flow.simulating:
                        frozen=PNMImage()
                        if not app.win.get_screenshot(frozen):raise RuntimeError('Pre-pause capture failed')
                        frozen=(frozen,visible_text(),telemetry())
                        game.keyboard('escape',True);game.keyboard('escape',False)
                    capture.append((command['id'],frozen));command=None
            dt=app._clock.get_dt()
            if app.state==GameState.PLAYING and game.flow.simulating:active+=min(max(dt,0),.25)
            game.frame(dt,look,(0,0));look=(0.,0.)
            if game._player.advanced is not None:raise RuntimeError('OFF session invalidated: movement was enabled')
            if active-last_sample>=.5:
                last_sample=active
                log('PlayerSample',dict(hp=game._fighter.hp,max_hp=game._fighter.max_hp,
                    stamina=game._fighter.stamina,max_stamina=game._fighter.stats.max_stamina,
                    player_state=game._player.state.value))
            return task.cont
        def observe(task):
            while capture:
                identity,frozen=capture.pop(0)
                if frozen:image,texts,metrics=frozen
                else:
                    image=PNMImage()
                    if not app.win.get_screenshot(image):raise RuntimeError('Game frame capture failed')
                    texts=visible_text()
                    metrics=telemetry()
                response=dict(id=identity,active_s=round(active,3),wall_s=round(time.monotonic()-started+wall_offset,3),
                    state=app.state.value,flow=game.flow.current.value,area=game.active_area,
                    visible_text=texts,telemetry=metrics,quarantined=monitor.quarantined,
                    capture_moment='last_presented_before_pause' if frozen else 'after_input')
                work.put(('image',(image,response)))
            return task.cont
        app.taskMgr.add(update,'balance-production-input',sort=10)
        app.taskMgr.add(observe,'balance-observation',sort=60)
        app.run()
        log('SessionStopped',dict(active_s_total=active))
    finally:
        app.destroy();work.put(None);work.join();worker.join(timeout=10)


if __name__=='__main__':main()
