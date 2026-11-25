from dataclasses import replace
import pytest
from advanced_fakes import scene
from combat_fakes import ContactFake,PhysicsFake
from vigilia.combat.fighter import Fighter
from vigilia.combat.orchestrator import CombatSystem
from vigilia.combat.events import DamageDealt,EntityDied,StaggerTriggered
from vigilia.core.events import EventBus,SlamImpactEvent
from vigilia.core.mathx import Transform,Vec3
from vigilia.core.types import Action,RayHit
from vigilia.entities.ecs import World
from vigilia.model.items import LONGSWORD_SPEC
from vigilia.model.attacks import AttackKind


class FloorPhysics(PhysicsFake):
    def raycast(self,origin,end):
        if end.z<=0<=origin.z:
            return RayHit(Vec3(origin.x,origin.y,0),Vec3(0,0,1),origin.z)
        return None


def dropping():
    s=scene();s.body.on_ground=False;s.player.transform.position=Vec3(0,0,4)
    s.movement.physics=FloorPhysics()
    return s


def test_slam_is_eighteen_m_per_second_vulnerable_and_spends_stamina_once():
    s=dropping();before=s.fighter.stamina
    assert s.step(Action.SLAM)==Vec3(0,0,-18)
    assert s.body.vertical_override and not s.fighter.invulnerable
    s.step(Action.SLAM)
    assert before-s.fighter.stamina==18
    assert not any(isinstance(e,SlamImpactEvent) for e in s.events)


def test_impact_emits_one_scaled_packet_and_blocks_actions_for_eight_steps():
    s=dropping();s.step(Action.SLAM);s.player.transform.position=Vec3(0,0,1)
    s.step();impacts=[e for e in s.events if isinstance(e,SlamImpactEvent)]
    assert len(impacts)==1 and impacts[0].radius==2.5 and impacts[0].poise==60
    packet=LONGSWORD_SPEC.attack(AttackKind.LIGHT_1).packet
    expected=sum(getattr(packet,k) for k in ('physical_slash','physical_strike','physical_pierce','fire','magic','holy'))*.4
    assert impacts[0].damage==pytest.approx(expected)
    assert s.movement.mode=='slam_recovery'
    for _ in range(7):
        s.step(Action.LIGHT)
        assert s.fighter.attack is None and not s.fighter.invulnerable
    assert s.movement.mode=='' and not s.body.vertical_override
    s.body.on_ground=True;s.step(Action.LIGHT)
    assert s.fighter.attack is not None
    assert len([e for e in s.events if isinstance(e,SlamImpactEvent)])==1


@pytest.mark.parametrize('state',['ground','stagger','dead','empty'])
def test_slam_is_rejected_when_not_available(state):
    s=dropping()
    if state=='ground':s.body.on_ground=True
    if state=='stagger':s.fighter.stagger_steps=10
    if state=='dead':s.fighter.hp=0
    if state=='empty':s.fighter.stamina=0
    s.step(Action.SLAM)
    assert not s.body.vertical_override and s.movement.mode!='slam'


def arena():
    world,bus,physics=World(),EventBus(),PhysicsFake()
    actors=[]
    for position in (Vec3(0,1,.85),Vec3(2.4,0,.85),Vec3(2.6,0,.85)):
        fighter=Fighter(1,LONGSWORD_SPEC.instantiate())
        entity=world.spawn(Transform(position),fighter)
        actors.append((entity,fighter))
    combat=CombatSystem(ContactFake(),physics,bus)
    return world,bus,physics,actors,combat


def test_mock_impact_resolves_multiple_targets_without_an_attacker_or_hitboxes():
    world,bus,physics,actors,combat=arena();events=[];stagger=[]
    bus.subscribe(DamageDealt,events.append);bus.subscribe(StaggerTriggered,stagger.append)
    before=[f.hp for _,f in actors]
    bus.publish(SlamImpactEvent(Vec3(),2.5,40,60))
    assert [f.hp for _,f in actors]==before  # Deferred until combat, after physics.
    combat.resolve(world)
    assert [e.target for e in events]==[actors[0][0].id,actors[1][0].id]
    assert all(e.source==-1 and e.attack_kind=='slam' for e in events)
    assert actors[2][1].hp==before[2] and len(stagger)==2
    after=[f.hp for _,f in actors];combat.resolve(world)
    assert [f.hp for _,f in actors]==after


def test_area_respects_iframes_walls_height_and_faction():
    world,bus,physics,actors,combat=arena()
    source=world.spawn(Transform(Vec3()),Fighter(0,LONGSWORD_SPEC.instantiate()))
    ally=Fighter(0,LONGSWORD_SPEC.instantiate());world.spawn(Transform(Vec3(0,1,.85)),ally)
    actors[0][1].invulnerable=True
    high=Fighter(1,LONGSWORD_SPEC.instantiate());world.spawn(Transform(Vec3(0,0,4)),high)
    initial=[f.hp for _,f in actors]+[ally.hp,high.hp]
    physics.wall=RayHit(Vec3(),Vec3(0,-1),.1)
    event=SlamImpactEvent(Vec3(),2.5,40,60,source.id)
    bus.publish(event);combat.resolve(world)
    assert [f.hp for _,f in actors]+[ally.hp,high.hp]==initial
    physics.wall=None;bus.publish(event);combat.resolve(world)
    assert actors[0][1].hp==initial[0] and actors[1][1].hp<initial[1]
    assert actors[2][1].hp==initial[2] and ally.hp==initial[3] and high.hp==initial[4]


def test_area_kill_publishes_existing_death_and_resistance_reduces_damage():
    world,bus,physics,actors,combat=arena();deaths=[];events=[]
    bus.subscribe(EntityDied,deaths.append);bus.subscribe(DamageDealt,events.append)
    actors[0][1].hp=1
    actors[1][1].resist=replace(actors[1][1].resist,physical_strike=80)
    bus.publish(SlamImpactEvent(Vec3(),2.5,40,60));combat.resolve(world)
    assert deaths==[EntityDied(actors[0][0].id)]
    assert events[1].amount<events[0].amount and actors[1][1].hp>0


@pytest.mark.parametrize('event',[SlamImpactEvent(Vec3(),0,40,60),
    SlamImpactEvent(Vec3(),2.5,float('nan'),60),SlamImpactEvent(Vec3(),2.5,40,-1)])
def test_invalid_impacts_are_rejected_before_mutating_combat(event):
    world,bus,physics,actors,combat=arena();before=[f.hp for _,f in actors]
    with pytest.raises(ValueError):bus.publish(event)
    combat.resolve(world);assert [f.hp for _,f in actors]==before


def test_player_can_take_real_damage_while_descending_and_recovering():
    for recovering in (False,True):
        s=dropping();s.step(Action.SLAM)
        if recovering:
            s.player.transform.position=Vec3(0,0,1);s.step()
        world,bus=World(),EventBus()
        world.spawn(Transform(s.player.transform.position),s.fighter)
        combat=CombatSystem(ContactFake(),PhysicsFake(),bus)
        before=s.fighter.hp
        bus.publish(SlamImpactEvent(s.player.transform.position,2.5,20,0,team=1))
        combat.resolve(world)
        assert s.fighter.hp<before and not s.fighter.invulnerable
