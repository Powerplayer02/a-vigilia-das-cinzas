import pytest
from advanced_fakes import scene
from vigilia.core.events import DashStartedEvent
from vigilia.core.timing import FIXED_DT
from vigilia.core.types import Action, HeldState
from vigilia.core.mathx import Vec3


@pytest.mark.parametrize('x,y', [(0,1),(1,1),(1,0),(1,-1),(0,-1),(-1,-1),(-1,0),(-1,1)])
def test_eight_directions_have_equal_4_5m_distance_in_twelve_steps(x, y):
    s = scene()
    held = HeldState(move_x=x, move_y=y)
    velocities = [s.step(Action.DASH, held)] + [s.step(held=held) for _ in range(11)]
    assert sum(v.length() * FIXED_DT for v in velocities) == pytest.approx(4.5)
    assert velocities[0].normalized().dot(Vec3(x,y).normalized()) == pytest.approx(1)
    assert not s.movement.dashing and s.movement.charges == 1
    assert len([e for e in s.events if isinstance(e, DashStartedEvent)]) == 1
    assert s.fighter.stamina == s.fighter.stats.max_stamina


@pytest.mark.parametrize('step,invulnerable', [(1,True),(6,True),(7,False),(12,False)])
def test_dash_iframes_are_exactly_first_six_steps(step, invulnerable):
    s = scene()
    s.step(Action.DASH)
    for _ in range(step-1): s.step()
    assert s.fighter.invulnerable is invulnerable


def test_two_charges_recover_sequentially_in_72_steps_each():
    s = scene()
    s.step(Action.DASH)
    s.step(Action.DASH)
    assert s.movement.charges == 0
    for _ in range(70): s.step()
    assert s.movement.charges == 0
    s.step()
    assert s.movement.charges == 1
    for _ in range(72): s.step()
    assert (s.movement.charges, s.movement.recharge) == (2,0)


def test_kill_refill_is_credited_once_and_clears_timer_at_full():
    s = scene()
    s.step(Action.DASH)
    s.step(Action.DASH)
    s.movement.on_kill(4)
    s.movement.on_kill(4)
    assert s.movement.charges == 1
    s.movement.on_kill(5)
    assert (s.movement.charges,s.movement.recharge) == (2,0)


@pytest.mark.parametrize('action', [Action.LIGHT,Action.HEAVY,Action.PARRY,Action.CAST])
def test_combat_actions_cancel_dash_and_remove_iframes(action):
    s = scene()
    s.step(Action.DASH)
    s.step(action)
    assert not s.movement.dashing and not s.fighter.invulnerable
    if action == Action.LIGHT: assert s.fighter.attack is not None
    if action == Action.PARRY: assert s.fighter.parry_step == 0


@pytest.mark.parametrize('dead', [False,True])
def test_dash_cannot_escape_stagger_or_death(dead):
    s = scene()
    s.fighter.hp = 0 if dead else s.fighter.hp
    s.fighter.stagger_steps = 0 if dead else 10
    s.step(Action.DASH)
    assert not s.movement.dashing and s.movement.charges == 2
    assert s.player.velocity == Vec3()


def test_dash_can_cancel_itself_but_not_when_charges_are_empty():
    s = scene()
    s.step(Action.DASH)
    s.step(Action.DASH,HeldState(move_x=1))
    before = s.movement.age
    s.step(Action.DASH,HeldState(move_x=-1))
    assert s.movement.age == before+1 and s.movement.direction.x == pytest.approx(1)
