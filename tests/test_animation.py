"""Animation interruption, timing boundaries and preparation preserve rules."""
import ast
import math
from pathlib import Path
from types import SimpleNamespace

import pytest
from vigilia.core.animation import AnimationView, PoseChannels, interpolate_pose
from vigilia.engine.animation import AnimationMixer, ATTACKS, WARMUP_CLIPS, sample
from vigilia.engine.render import ArenaRenderer
from vigilia.engine.particles import ParticleEmitter,ParticlePool
from vigilia.core.mathx import Vec3,Transform
from vigilia.core.types import GameState
from vigilia.combat.fighter import Fighter
from vigilia.entities.ecs import World
from vigilia.model.items import WEAPONS,PLAYER_WEAPON_IDS
from vigilia.player.controller import PlayerState
from vigilia.game import Game


@pytest.mark.parametrize('attack',ATTACKS)
def test_attack_stages_meet_without_a_pose_jump(attack):
    assert sample(attack+':windup',1)==sample(attack+':active',0)
    assert sample(attack+':active',1)==sample(attack+':recovery',0)
    assert sample(attack+':recovery',1)==PoseChannels()


def test_four_rolls_keep_distinct_axes_and_return_to_same_orientation():
    poses=[sample('roll_'+name,.5) for name in ('forward','back','left','right')]
    assert len(set(poses))==4
    assert all(p.height<0 for p in poses)
    for name in ('forward','back','left','right'):
        end=sample('roll_'+name,1)
        assert end.pitch%360==end.roll%360==0


def test_all_clips_stay_finite_at_frame_boundaries_and_support_all_boss_phases():
    for clip in WARMUP_CLIPS:
        for phase in (1,2,3):
            for progress in (0,1/60,.5,59/60,1):
                assert all(math.isfinite(v) for v in sample(clip,progress,speed=5.8,phase=phase,profile='boss:forge_custodian'))


def test_pause_freezes_cues_and_pose_then_resumes_without_restarting():
    mixer=AnimationMixer();mixer.cue('drink',.8)
    pose=mixer.step(AnimationView(),.2)
    assert mixer.step(AnimationView(paused=True),10)==pose
    assert mixer.cue_remaining==pytest.approx(.6)
    mixer.step(AnimationView(),.1)
    assert mixer.cue_remaining==pytest.approx(.5)


def test_interrupted_roll_does_not_unwind_an_extra_full_turn():
    mixer=AnimationMixer()
    mixer.step(AnimationView('rolling',1,direction=0),.2)
    pose=mixer.step(AnimationView(),.02)
    assert abs(pose.pitch+360)<5
    assert interpolate_pose(PoseChannels(pitch=179),PoseChannels(pitch=-179),.5).pitch==180


def test_corpse_loaded_while_paused_has_its_final_pose():
    mixer=AnimationMixer()
    assert mixer.step(AnimationView('death',paused=True),0).pitch==82
    assert mixer.step(AnimationView('death'),1/60).pitch==82


def test_roll_loaded_while_paused_uses_saved_progress_without_a_neutral_frame():
    mixer=AnimationMixer()
    view=AnimationView('rolling',.5,direction=math.pi/2,paused=True)
    assert mixer.step(view,0).roll==180
    assert mixer.step(AnimationView('rolling',.5,direction=math.pi/2),1/60).roll==180


def test_phase_preparation_only_queues_existing_resources_once():
    calls=[]
    class Node:
        def prepare_scene(self,gsg):calls.append(gsg)
    renderer=ArenaRenderer.__new__(ArenaRenderer)
    renderer._app=SimpleNamespace(render=Node(),win=SimpleNamespace(get_gsg=lambda:'gsg'))
    renderer._phase_prepares=set();renderer._phase_prepared=set()
    renderer._enemies={10:(Node(),None,None)};renderer._combat_gear={10:(Node(),)}
    renderer.queue_phase_warmup(10,3);renderer.prepare_phase_resources()
    renderer.queue_phase_warmup(10,3);renderer.prepare_phase_resources()
    assert calls==['gsg']*3
    assert renderer._phase_prepares==set()


def test_presentation_sampler_does_not_depend_on_combat_or_physics():
    path=Path(__file__).parents[1]/'src/vigilia/engine/animation.py'
    tree=ast.parse(path.read_text(encoding='utf8'))
    modules=[node.module or '' for node in ast.walk(tree) if isinstance(node,ast.ImportFrom)]
    assert all(not name.startswith(('vigilia.combat','vigilia.player','vigilia.model','panda3d')) for name in modules)


def test_particle_warmup_restores_live_slots_free_order_and_rng_after_failure():
    emitter=ParticleEmitter.__new__(ParticleEmitter);emitter.pool=ParticlePool(40,seed=7)
    emitter.update=lambda dt:emitter.pool.update(dt)
    emitter.pool.spawn('souls',Vec3(2,3,4),count=6)
    from dataclasses import asdict
    before=([asdict(p) for p in emitter.pool.slots],emitter.pool._free.copy(),emitter.pool._rng.getstate())
    with pytest.raises(RuntimeError):
        with emitter.warmup():raise RuntimeError('injected render failure')
    assert before==([asdict(p) for p in emitter.pool.slots],emitter.pool._free,emitter.pool._rng.getstate())


def test_game_animation_view_uses_authoritative_attack_age_without_advancing_it():
    game=Game.__new__(Game);game._world=World()
    spec=WEAPONS[PLAYER_WEAPON_IDS[0]];fighter=Fighter(0,spec.instantiate())
    game._entity=game._world.spawn(Transform(),fighter)
    game._player=SimpleNamespace(velocity=Vec3(),state=PlayerState.IDLE)
    game._commands=SimpleNamespace(charge=0);game._app=SimpleNamespace(state=GameState.PLAYING)
    game.boss=None;game._has_session=True
    definition=spec.attacks[0];fighter.start(definition)
    for age,stage in ((0,'windup'),(definition.windup,'active'),(definition.windup+definition.active,'recovery')):
        fighter.attack.age=age
        before=fighter.to_snapshot({game._entity.id:'player'})
        assert game._animation_view(game._entity,fighter).action.endswith(':'+stage)
        assert fighter.to_snapshot({game._entity.id:'player'})==before


def test_hud_bar_easing_accepts_a_new_target_mid_transition():
    from panda3d.core import NodePath
    from vigilia.engine.ui import PandaUIBackend
    backend=PandaUIBackend.__new__(PandaUIBackend)
    backend.root=NodePath('ui');backend.nodes={'hp':NodePath('fill')}
    backend._bar_targets={};backend._bar_active=set();backend._panel_fades={};backend._closing_panels=[]
    backend._transition_age=.15
    backend.fraction('hp',1);backend.fraction('hp',.2);backend.tick(.04)
    assert .2<backend.nodes['hp'].get_sx()<1
    backend.fraction('hp',.8)
    for _ in range(60):backend.tick(1/60)
    assert backend.nodes['hp'].get_sx()==pytest.approx(.8)
    assert not backend._bar_active


def test_menu_closed_mid_fade_does_not_flash_back_to_full_opacity():
    from panda3d.core import NodePath
    from vigilia.engine.ui import PandaUIBackend
    backend=PandaUIBackend.__new__(PandaUIBackend)
    backend.root=NodePath('ui');backend.nodes={}
    backend._bar_active=set();backend._panel_fades={};backend._transition_age=.15
    ghost=NodePath('closing');ghost.set_alpha_scale(.25)
    backend._closing_panels=[[ghost,0.,.25]]
    backend.tick(.075)
    assert ghost.get_color_scale().w==pytest.approx(.125)
    backend.tick(.075)
    assert not backend._closing_panels
