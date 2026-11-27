"""Procedural articulated animation. No physics, combat or native dependency.

Action age/progress comes from the authoritative 60Hz simulation. The mixer
interpolates presentation only; it cannot advance attacks or contact volumes.
"""
import math

from vigilia.core.animation import AnimationView, PoseChannels, interpolate_pose, smoothstep


P = PoseChannels
NEUTRAL = P()
# Key poses share the same prepared geometry and render state in every clip.
ATTACKS = {
    'light_1': (P(yaw=-12, torso=-9, right_leg=12), P(yaw=18, torso=13, left_leg=-12)),
    'light_2': (P(yaw=18, torso=-7, left_leg=14), P(yaw=-21, torso=15, right_leg=-12)),
    'light_3': (P(pitch=-8, torso=-18, head=9), P(pitch=12, torso=25, right_leg=-18)),
    'heavy': (P(pitch=-8, torso=-24, head=12), P(pitch=14, torso=32, left_leg=-20)),
    'running': (P(pitch=9, torso=-12, right_leg=22), P(pitch=18, torso=20, left_leg=-22)),
    'dash_attack': (P(pitch=14, yaw=-15), P(pitch=22, yaw=18, right_leg=-24)),
    'sliding': (P(pitch=-9, height=-.22, left_leg=50), P(pitch=12, yaw=16, height=-.25, left_leg=64)),
    'walking_attack': (P(yaw=-8, torso=-6), P(yaw=14, torso=12)),
    'riposte': (P(torso=-18, right_leg=20), P(pitch=12, torso=22, left_leg=-24)),
    'backstab': (P(yaw=-14, torso=-12), P(pitch=16, torso=18, right_leg=-24)),
    'slow_overhead': (P(pitch=-10, torso=-25, head=14), P(pitch=16, torso=30, left_leg=-25)),
    'wide_sweep': (P(yaw=-24, torso=-9, roll=-5), P(yaw=26, torso=12, roll=7)),
    'backstep_punish': (P(pitch=-8, right_leg=20), P(pitch=22, torso=16, left_leg=-25)),
    'forge_grab': (P(pitch=-10, torso=-16), P(pitch=20, torso=17, left_leg=-18)),
    'fire_aoe_ring': (P(pitch=-8, torso=-20, head=-18), P(pitch=18, height=-.18, torso=24)),
    'tide_strike': (P(torso=-18, yaw=-12), P(torso=24, yaw=15)),
    'tide_sweep': (P(yaw=22, roll=7), P(yaw=-24, roll=-6)),
    'tide_bolt': (P(torso=-13, head=-9), P(torso=14, head=9)),
    'tide_grasp': (P(torso=-18, yaw=12), P(pitch=16, yaw=-15)),
    'tide_nova': (P(pitch=-13, torso=-18), P(pitch=14, height=-.16)),
    'arcane_bolt': (P(torso=-10, head=-8), P(torso=12, head=6)),
    'mending_light': (P(torso=-8, head=-12), P(torso=6, head=-18)),
    'practice': (P(torso=-8), P(torso=12)),
}
SPECIALS = ('idle','walk','run','roll_forward','roll_back','roll_left','roll_right',
    'backstep','block','block_hit','parry','hit','stagger','knockdown','drink','use_item',
    'interact','death_front','death_back','death_fire','death_fall','wall_cling',
    'airborne','slamming','slam_recovery','dashing','sliding','intro','phase','charging')
WARMUP_CLIPS = SPECIALS + tuple(name + ':' + stage for name in ATTACKS for stage in ('windup','active','recovery'))


def sample(action: str, progress: float, *, speed=0., phase=1, profile='player') -> PoseChannels:
    """Sample a normalized pose; action stages never alter hitbox trajectories."""
    p = max(0., min(1., progress)); pulse = math.sin(math.pi * p)
    if ':' in action:
        name, stage = action.split(':', 1)
        windup, impact = ATTACKS.get(name, ATTACKS['light_1'])
        follow=interpolate_pose(impact,NEUTRAL,.35)
        if stage == 'windup':
            if p<.85:
                result=interpolate_pose(NEUTRAL,windup,smoothstep(p/.85))
                strike=0.
            else:
                strike=smoothstep((p-.85)/.15)
                result=interpolate_pose(windup,impact,strike)
        elif stage == 'active':
            result=interpolate_pose(impact,follow,smoothstep(p))
            strike=1-.35*smoothstep(p)
        else:
            result=interpolate_pose(follow,NEUTRAL,smoothstep(p))
            strike=.65*(1-smoothstep(p))
        if profile.startswith('boss:') and phase>=2:
            result=result._replace(torso=result.torso*(1+.06*(phase-1)),
                head=result.head-4*(phase-1)*strike,roll=result.roll*(1+.06*(phase-1)))
        return result
    if action in ('walk','run'):
        wave = math.sin(math.tau * p); running = min(1., max(0., (speed - 3.1) / 2.7))
        reach = 26 + 17 * running
        return P(pitch=running*6, roll=wave*2, height=abs(wave)*(.025+.025*running),
            torso=-running*4, head=-running*3, left_leg=wave*reach, right_leg=-wave*reach,
            left_arm=-wave*18, right_arm=wave*18,
            left_knee=max(0.,-wave)*36, right_knee=max(0.,wave)*36)
    if action.startswith('roll_'):
        angle = -360 * p
        return P(pitch=angle if action=='roll_forward' else -angle if action=='roll_back' else 0,
            roll=angle if action=='roll_left' else -angle if action=='roll_right' else 0,
            height=-.22*pulse, torso=26*pulse, left_leg=32*pulse, right_leg=32*pulse,
            left_knee=65*pulse,right_knee=65*pulse)
    if action == 'backstep': return P(pitch=-18*pulse, height=-.1*pulse, left_leg=24*pulse, right_leg=24*pulse)
    if action.startswith('death_'):
        fall = smoothstep(p)
        if action=='death_back': return P(pitch=-85*fall, height=-.62*fall, left_leg=12*fall, right_leg=-10*fall)
        if action=='death_fire': return P(pitch=76*fall, roll=12*math.sin(p*math.tau*3)*(1-p), height=-.62*fall, head=-25*fall)
        if action=='death_fall': return P(pitch=88*fall, height=-.64*fall, left_leg=-24*fall, right_leg=28*fall)
        return P(pitch=82*fall, height=-.62*fall, torso=15*fall, head=18*fall)
    if action in ('hit','stagger','block_hit'):
        strength=1.7 if action=='stagger' else .5 if action=='block_hit' else 1
        hold=smoothstep(p) if action=='stagger' else 0
        return P(pitch=-11*pulse*strength+8*hold,torso=16*hold,
            roll=5*pulse*strength,head=15*pulse*strength+18*hold,left_leg=8*pulse)
    if action=='knockdown': return P(pitch=78, height=-.08, left_leg=12, right_leg=-8)
    if action=='parry': return P(yaw=-14*pulse, torso=-6*pulse, left_arm=-75*pulse)
    if action=='block': return P(pitch=4, torso=-3, head=4, left_leg=8,right_leg=-9)
    if action in ('drink','use_item'): return P(torso=-5*pulse, head=-18*pulse, right_arm=-120*pulse)
    if action=='interact': return P(torso=20*pulse, head=14*pulse, right_arm=-65*pulse)
    if action in ('intro','phase'):
        return P(pitch=-9*pulse, torso=-14*pulse, head=-25*pulse,
            yaw=math.sin(p*math.tau)*4*(phase-1), left_arm=-55*pulse, right_arm=-65*pulse)
    if action=='wall_cling': return P(pitch=-7, left_arm=-140,right_arm=-135,left_leg=32,right_leg=20,left_knee=65,right_knee=50)
    if action=='airborne': return P(pitch=8, left_leg=25,right_leg=-12,left_knee=45,right_knee=25)
    if action=='slamming': return P(pitch=25, torso=18,left_leg=30,right_leg=30,left_knee=70,right_knee=70)
    if action=='slam_recovery': return P(pitch=18*(1-p),height=-.3*(1-p),left_knee=65*(1-p),right_knee=65*(1-p))
    if action in ('sliding','dashing'): return P(pitch=22 if action=='dashing' else -12,height=0 if action=='dashing' else -.38,left_leg=55,right_leg=-15,left_knee=30)
    if action=='charging': return P(torso=-20,head=8,right_leg=16)
    breath=math.sin(math.tau*p)
    crouch=5 if profile in ('rancor','bog_ghoul') else -2 if profile=='ossuary_acolyte' else 0
    # Breathing is local to chest/head; idle must not dirty every child matrix.
    return P(torso=breath*.8+crouch,head=-breath)


class AnimationMixer:
    """A short crossfade with persistent stride and presentation-only cues."""
    def __init__(self):
        self.action='';self.age=self.stride=self.fade=0.
        self.pose=self.previous=NEUTRAL
        self.cue_action='';self.cue_remaining=self.cue_duration=0.
        self.death='death_front'
        self.last_direction=0.
        self._target_key=None;self._target=NEUTRAL

    def cue(self,action,duration):
        if action.startswith('death_'): self.death=action
        else:
            self.cue_action,self.cue_remaining,self.cue_duration=action,duration,duration
            if self.action==action:self.previous=self.pose;self.age=self.fade=0.

    def step(self,view: AnimationView,dt: float):
        initial=not self.action
        if view.paused and self.action:return self.pose
        if not self.action and view.action=='death':
            self.action=self.death;self.pose=sample(self.death,1)
            self.age=2.2 if view.profile.startswith('boss:') else 1.1
            self.fade=.085;self.previous=self.pose
            return self.pose
        dt=max(0.,dt);self.stride+=view.speed*dt*2.8
        self.cue_remaining=max(0.,self.cue_remaining-dt)
        action=view.action
        progress=view.progress
        if action=='death':action=self.death
        elif action in ('idle','walk','run','block') and self.cue_remaining:
            action=self.cue_action;progress=1-self.cue_remaining/max(.001,self.cue_duration)
        if action=='rolling':
            if self.action not in ('roll_forward','roll_back','roll_left','roll_right'):self.last_direction=view.direction
            sector=round(self.last_direction/(math.pi/2)) % 4
            action=('roll_forward','roll_right','roll_back','roll_left')[sector]
        if action!=self.action:
            old_parts=self.action.split(':');new_parts=action.split(':')
            same_attack=(len(old_parts)==len(new_parts)==2 and old_parts[0]==new_parts[0]
                and (old_parts[1],new_parts[1]) in (('windup','active'),('active','recovery')))
            self.previous=self.pose;self.action=action;self.age=self.fade=0.
            # These stages already have continuous key poses. A second crossfade
            # would delay the visible strike after the authoritative active age.
            if same_attack:self.fade=.085
        self.age+=dt;self.fade+=dt
        if progress is None:
            if action in ('walk','run'):
                progress=(self.stride/math.tau)%1
            elif action.startswith('death_'):
                duration=2.2 if view.profile.startswith('boss:') else 1.1
                progress=min(1.,self.age/duration)
            elif action in ('idle','block','wall_cling','airborne'):
                progress=(self.age/3)%1
            else:
                progress=min(1.,self.age/.4)
        key=(action,progress,view.speed,view.phase,view.profile)
        if key!=self._target_key:
            self._target=sample(action,progress,speed=view.speed,phase=view.phase,profile=view.profile)
            self._target_key=key
        target=self._target
        self.pose=interpolate_pose(self.previous,target,smoothstep(self.fade/.085)) if self.fade<.085 and not initial else target
        if initial:self.previous=target;self.fade=.085
        return self.pose
