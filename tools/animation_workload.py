"""Explicit catalog-pose stress fixture over the production gameplay loop.

This controls presentation inputs only. It is not a player input playthrough,
not human balance evidence, and does not alter fighter timers or hitboxes.
"""
import time
from vigilia.core.animation import AnimationView
from vigilia.engine.animation import WARMUP_CLIPS


class AnimationWorkload:
    def __init__(self,renderer):
        self.original=renderer.animate_actor
        self.renderer=renderer
        self.started=None;self.seconds=0.;self.calls=0;self.max_seconds=0.
        self.seen={}
        renderer.animate_actor=self.animate

    def begin(self):self.started=time.perf_counter()

    def animate(self,identifier,view):
        if self.started is None:return self.original(identifier,view)
        mixer=self.renderer._animation_mixers.get(identifier)
        if mixer is None:return self.original(identifier,view)
        elapsed=time.perf_counter()-self.started
        position=elapsed/.35;index=int(position)+identifier*13
        clip=WARMUP_CLIPS[index%len(WARMUP_CLIPS)]
        phase=1+(index//len(WARMUP_CLIPS))%3 if view.profile.startswith('boss:') else 1
        override=AnimationView(clip,position%1,5.8 if clip=='run' else 3.1 if clip=='walk' else view.speed,
            view.direction,view.profile,phase,False)
        # The stress fixture overrides presentation cues as well as poses.
        # Damage/attack rules and audio still use the production loop.
        mixer.cue_remaining=0
        start=time.perf_counter()
        self.original(identifier,override)
        duration=time.perf_counter()-start
        actual=mixer.action
        self.seen.setdefault(view.profile,set()).add(f'{phase}:{actual}' if view.profile.startswith('boss:') else actual)
        self.calls+=1;self.seconds+=duration;self.max_seconds=max(self.max_seconds,duration)

    def report(self,frames):
        return dict(kind='Catalog poses over production combat; not a player-input playthrough',
            pose_interval_s=.35,expected_clips=list(WARMUP_CLIPS),
            timed_scope='ArenaRenderer.animate_actor: mixer/transforms; excludes weapon/contact synchronization',
            seen={role:sorted(clips) for role,clips in self.seen.items()},calls=self.calls,
            animation_mean_ms_per_render=self.seconds*1000/max(1,frames),
            actor_mean_us=self.seconds*1e6/max(1,self.calls),actor_max_ms=self.max_seconds*1000)
