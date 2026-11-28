"""Visual emitters with distance/density LOD. No game-state or physics writes."""
import math
import random

from vigilia.core.mathx import Vec3


AREA_EFFECTS={
    'patio_da_vigilia':(('ash',2.),),
    'catedral_submersa':(('motes',7.),),
    'pantano_das_cinzas':(('mist',3.),('rain',32.),('splash',6.)),
    'ruinas_subterraneas':(('dust',5.),('debris',.7)),
    'forno_da_vigilia':(('flame',6.),('sparks',5.),('ash',8.)),
}


class ParticleScene:
    """One shared pool. Ambience cannot consume the reserved combat budget."""
    def __init__(self,emitter,*,seed=271):
        self.emitter=emitter;self.rng=random.Random(seed)
        self.enabled=True;self.area='';self.fires=();self.elapsed=0.
        self._credits={};self._fire_credits=0.

    def set_area(self,area,fires=()):
        if area not in AREA_EFFECTS:raise ValueError('Área visual desconhecida')
        self.area=area;self.fires=tuple(fires);self.elapsed=0.
        self._credits={name:0. for name,_ in AREA_EFFECTS[area]};self._fire_credits=0.

    def update(self,dt,target=Vec3(),*,paused=False):
        if paused or not self.enabled or not self.area or dt<=0:return
        # Do not backfill seconds of ambience after a stall/tab-out.
        dt=min(dt,.1);self.elapsed+=dt
        for preset,rate in AREA_EFFECTS[self.area]:
            credit=self._credits[preset]+rate*dt
            count=int(credit);self._credits[preset]=credit-count
            for _ in range(count):
                angle=self.rng.uniform(0,math.tau);distance=self.rng.uniform(2,10)
                height=self.rng.uniform(3,5) if preset in ('rain','debris') else self.rng.uniform(.2,2)
                if preset in ('mist','splash','flame'):height=-.8 if preset in ('splash','flame') else -.6
                position=target+Vec3(math.cos(angle)*distance,math.sin(angle)*distance,height)
                self.emitter.spawn_lod(preset,position,distance=distance,ambient=True,count=1)
        self._fire_credits+=dt*12
        fire_count=int(self._fire_credits);self._fire_credits-=fire_count
        if fire_count:
            for fire in self.fires:
                distance=(fire-target).length()
                for preset in ('flame','embers','smoke'):
                    self.emitter.spawn_lod(preset,fire+Vec3(0,0,.25),distance=distance,
                        ambient=True,count=max(1,fire_count//2))

    def movement(self,position,*,water=False):
        if self.enabled:self.emitter.spawn_lod('splash' if water else 'dust',position-Vec3(0,0,.85),count=5)

    def phase(self,position,phase,*,water=False):
        if not self.enabled:return
        self.emitter.spawn_lod('splash' if water else 'flame',position,count=12*phase)
        self.emitter.spawn_lod('mist' if water else 'ash',position,count=6*phase)
