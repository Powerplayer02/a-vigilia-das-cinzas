import math
import pytest
from advanced_fakes import scene
from combat_fakes import PhysicsFake
from vigilia.core.events import WallClingStartedEvent, WallJumpStartedEvent
from vigilia.core.mathx import Vec3
from vigilia.core.types import Action, HeldState, RayHit


class WallPhysics(PhysicsFake):
    def __init__(self, normal=Vec3(0,-1,0)):
        super().__init__();self.normal=normal;self.calls=[];self.surface=None

    def raycast(self, origin, end):
        self.calls.append((origin,end))
        return RayHit(origin+(end-origin).normalized()*.45,self.normal,.45,self.surface)


def airborne(normal=Vec3(0,-1,0)):
    s=scene();s.body.on_ground=False;s.player.transform.position=Vec3(0,0,3)
    s.movement.physics=WallPhysics(normal)
    return s


def test_frontal_half_meter_ray_enters_cling_and_freezes_both_velocities():
    s=airborne();v=s.step(held=HeldState(move_y=1))
    assert s.movement.mode=='wall_cling' and s.body.vertical_override
    assert v==Vec3() and not s.fighter.invulnerable
    origin,end=s.movement.physics.calls[0]
    assert (end-origin).length()==pytest.approx(.5)
    assert isinstance(s.events[-1],WallClingStartedEvent)


@pytest.mark.parametrize('normal',[Vec3(0,0,1),Vec3(0,1,0),Vec3(1,0,0)])
def test_floor_receding_and_tangential_surfaces_are_not_climbable(normal):
    s=airborne(normal);s.step(held=HeldState(move_y=1))
    assert not s.movement.used_walls and s.movement.mode!='wall_cling'


def test_cling_expires_at_24_steps_and_same_wall_cannot_regrab_in_air():
    s=airborne();held=HeldState(move_y=1);s.step(held=held)
    for _ in range(23):s.step(held=held)
    assert s.movement.mode==''
    v=s.step(held=held)
    assert v.z<0 and s.movement.mode!='wall_cling'
    assert len([e for e in s.events if isinstance(e,WallClingStartedEvent)])==1
    s.body.on_ground=True;s.step()
    assert not s.movement.used_walls and not s.body.vertical_override
    s.body.on_ground=False;s.step(held=held)
    assert s.movement.mode=='wall_cling'


def test_wall_jump_launches_away_with_thirty_percent_more_height():
    s=airborne();held=HeldState(move_y=1);s.step(held=held)
    before=s.fighter.stamina
    v=s.step(Action.JUMP,held)
    assert v.y<0 and v.z>0 and s.movement.mode==''
    assert (v.z+20/60)**2==pytest.approx(7**2*1.3)
    assert before-s.fighter.stamina==12
    assert any(isinstance(e,WallJumpStartedEvent) for e in s.events)
    s.step(held=held)
    assert s.movement.mode!='wall_cling'


def test_different_wall_is_available_but_not_original_plane():
    s=airborne();s.step(held=HeldState(move_y=1));s.step(Action.JUMP)
    s.movement.physics.normal=Vec3(-1,0,0)
    s.step(held=HeldState(move_x=1))
    assert s.movement.mode=='wall_cling' and len(s.movement.used_walls)==2


@pytest.mark.parametrize('x,y,allowed',[(0,1,False),(1,0,True),(0,-1,True)])
def test_cling_dash_only_allows_parallel_or_away(x,y,allowed):
    s=airborne();s.step(held=HeldState(move_y=1))
    s.step(Action.DASH,HeldState(move_x=x,move_y=y))
    assert s.movement.dashing==allowed
    assert s.movement.charges==(1 if allowed else 2)


def test_damage_cancels_cling_and_cannot_be_used_to_regrab():
    s=airborne();held=HeldState(move_y=1);s.step(held=held)
    s.movement.on_damage();s.step(held=held)
    assert s.movement.mode=='' and not s.body.vertical_override
    s.step(held=held)
    assert s.movement.mode!='wall_cling'


def test_insufficient_stamina_does_not_create_a_free_wall_jump():
    s=airborne();s.step(held=HeldState(move_y=1));s.fighter.stamina=0
    s.step(Action.JUMP)
    assert s.movement.mode=='wall_cling'


def test_surface_identity_blocks_same_wall_despite_normal_noise_but_allows_another_wall():
    s=airborne();s.movement.physics.surface='wall-a'
    held=HeldState(move_y=1);s.step(held=held);s.step(Action.JUMP)
    s.movement.physics.normal=Vec3(.01,-.99995,0)
    s.step(held=held)
    assert s.movement.mode!='wall_cling'
    s.movement.physics.surface='wall-b';s.movement.physics.normal=Vec3(0,-1,0)
    s.step(held=held)
    assert s.movement.mode=='wall_cling'
