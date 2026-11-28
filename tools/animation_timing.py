"""Direct CPU-presentation wall timings, independent of PStats/cProfile."""
import math
import statistics
import time


class AnimationTiming:
    def __init__(self,game,*,clock=None):
        self.clock=clock or time.perf_counter
        self.enabled=False;self.totals={};self.frame_ms=[];self.current=0.;self.samples={}
        self.inclusive_ms=[];self.inclusive_current=0.
        for owner,name,label in ((game,'_evaluate_poses','authoritative_pose'),
            (game,'_animation_view','view'),(game._renderer,'animate_actor','mixer_transform'),
            (game._renderer,'combat_pose','weapon_pose'),(game,'_draw_combat','presentation'),
            (game,'_fixed_step','fixed_step'),(getattr(game,'_particles',None),'update','particles'),
            (getattr(game,'_particle_scene',None),'update','particle_emitters'),
            (game,'frame','frame_update'),(game._renderer,'draw','scene_draw')):
            if hasattr(owner,name):self.wrap(owner,name,label)

    def wrap(self,owner,name,label):
        original=getattr(owner,name)
        def measured(*args,**kwargs):
            if not self.enabled:return original(*args,**kwargs)
            start=self.clock()
            try:return original(*args,**kwargs)
            finally:
                elapsed=self.clock()-start
                row=self.totals.setdefault(label,[0,0.,0.])
                row[0]+=1;row[1]+=elapsed;row[2]=max(row[2],elapsed)
                if label in ('fixed_step','particles','particle_emitters'):self.samples.setdefault(label,[]).append(elapsed*1000)
                # These scopes do not nest each other. Do not add the outer
                # presentation scope a second time or mix per-step averages.
                if label in ('authoritative_pose','view','mixer_transform'):self.current+=elapsed
                if label in ('authoritative_pose','presentation'):self.inclusive_current+=elapsed
        setattr(owner,name,measured)

    def begin(self):
        self.enabled=True;self.totals={};self.frame_ms=[];self.current=0.;self.samples={}
        self.inclusive_ms=[];self.inclusive_current=0.
    def begin_render(self):self.current=0.;self.inclusive_current=0.
    def end_render(self):
        if self.enabled:
            self.frame_ms.append(self.current*1000)
            self.inclusive_ms.append(self.inclusive_current*1000)

    def report(self):
        frames=max(1,len(self.frame_ms));ordered=sorted(self.frame_ms)
        return dict(instrument='perf_counter, no PStats/cProfile; direct wall time on the game thread',
            scope='Authoritative logical pose + AnimationView + mixer/native transform application; excludes weapon sync and GPU submission',
            render_frames=len(self.frame_ms),
            animation_total_mean_ms_per_render=statistics.mean(ordered) if ordered else None,
            animation_total_median_ms_per_render=statistics.median(ordered) if ordered else None,
            animation_total_p95_ms_per_render=ordered[math.ceil(len(ordered)*.95)-1] if ordered else None,
            animation_total_max_ms_per_render=max(ordered) if ordered else None,
            inclusive_scope='Authoritative pose + entire combat presentation including weapon sync/feedback; conservative upper bound, without nested double counting',
            animation_inclusive_median_ms_per_render=statistics.median(self.inclusive_ms) if self.inclusive_ms else None,
            animation_inclusive_p95_ms_per_render=sorted(self.inclusive_ms)[math.ceil(len(self.inclusive_ms)*.95)-1] if self.inclusive_ms else None,
            frame_inclusive_ms=self.inclusive_ms,
            stages={name:dict(calls=row[0],mean_ms_per_call=row[1]*1000/max(1,row[0]),
                total_ms_per_render=row[1]*1000/frames,max_ms=row[2]*1000)
                for name,row in self.totals.items()},
            frame_animation_ms=self.frame_ms,
            direct_scopes={name:dict(calls=len(values),median_ms=statistics.median(values),
                p95_ms=sorted(values)[math.ceil(len(values)*.95)-1],samples_ms=values)
                for name,values in self.samples.items()})
