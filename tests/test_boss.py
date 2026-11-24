"""Limiares, escolhas de ataques, interrupções e relógios do primeiro chefe."""

from dataclasses import replace

import pytest

from boss_fakes import encounter, PROFILE_PATH
from vigilia.ai.bosses import PhaseTransitionEvent
from vigilia.combat.attack import Attack, AttackKind
from vigilia.combat.events import HPChangedEvent, EntityDied, StaggerTriggered, ParrySucceeded
from vigilia.core.events import BossArenaEnteredEvent, BossDefeatedEvent, MusicChangeRequestedEvent, ItemUseStartedEvent
from vigilia.core.mathx import Vec3
from vigilia.entities.components import AttackIntent
from vigilia.model.bosses import load_boss_profile
from vigilia.model.items import LONGSWORD_SPEC


def test_profile_has_numeric_movesets_and_derived_resources():
    e = encounter()
    assert (e.fighter.hp, e.fighter.poise) == (3200, 180)
    assert len(e.profile.moveset(1)) == 3 and len(e.profile.moveset(2)) == 5
    assert [(m.windup, m.active, m.recovery) for m in e.profile.moveset(2)] == [
        (54, 12, 54), (30, 9, 36), (12, 6, 18), (42, 6, 78), (60, 30, 120)]
    assert e.fighter.backstab_immune


def test_arena_event_starts_180_step_intro_and_phase1_music():
    e, music = encounter(), []
    e.bus.subscribe(MusicChangeRequestedEvent, music.append)
    e.bus.publish(BossArenaEnteredEvent(e.profile.id, e.profile.arena, Vec3()))
    for _ in range(180):
        e.boss.tick(e.world)
        assert e.fighter.invulnerable
        assert e.world.get(e.entity, AttackIntent).definition is None
    e.boss.tick(e.world)
    assert not e.fighter.invulnerable
    assert [event.track_id for event in music] == ["boss_phase1"]


def test_phase_event_filters_entity_and_exact_half_then_protects_90_steps():
    e, phases, music = encounter(), [], []
    e.boss.start()
    e.bus.subscribe(PhaseTransitionEvent, phases.append)
    e.bus.subscribe(MusicChangeRequestedEvent, music.append)
    e.bus.publish(HPChangedEvent(e.player.id, 2000, 1000, 3200, "self"))
    e.bus.publish(HPChangedEvent(e.entity.id, 3200, 1600, 3200, "player"))
    assert e.boss.phase == 1
    e.fighter.hp = 1599
    e.bus.publish(HPChangedEvent(e.entity.id, 1600, 1599, 3200, "player"))
    assert phases == [PhaseTransitionEvent(e.profile.id, 2)]
    assert music[-1].track_id == "boss_phase2"
    for _ in range(90):
        e.boss.tick(e.world)
        assert e.fighter.invulnerable
    e.boss.tick(e.world)
    assert not e.fighter.invulnerable
    e.bus.publish(HPChangedEvent(e.entity.id, 1599, 500, 3200, "dot"))
    assert len(phases) == 1


@pytest.mark.parametrize("roll,kind", [(0.2, AttackKind.SLOW_OVERHEAD), (.9, AttackKind.WIDE_SWEEP)])
def test_phase1_weighted_selection_uses_injected_random(roll, kind):
    class FixedRandom:
        def random(self):
            return roll
    e = encounter(rng=FixedRandom())
    e.boss.active = True
    e.boss.tick(e.world)
    assert e.world.get(e.entity, AttackIntent).definition.kind == kind


@pytest.mark.parametrize("distance,blocking,kind", [
    (2.6, True, AttackKind.FORGE_GRAB), (1.5, False, AttackKind.FIRE_AOE_RING)])
def test_phase2_reactions_require_consecutive_steps_and_set_cooldown(distance, blocking, kind):
    e = encounter(distance)
    e.boss.active, e.boss.phase = True, 2
    e.hero.blocking = blocking
    # Outra ação em execução impede começar o especial antes da janela exigida.
    e.fighter.attack = Attack(e.profile.moveset(1)[0])
    trigger = 15 if blocking else 30
    for _ in range(trigger - 1):
        e.boss.tick(e.world)
        assert e.world.get(e.entity, AttackIntent).definition is None
    e.fighter.attack = None
    e.boss.tick(e.world)
    assert e.world.get(e.entity, AttackIntent).definition.kind == kind
    assert (e.boss.grab_cooldown if blocking else e.boss.aoe_cooldown) == (240 if blocking else 300)


def test_estus_event_and_combo_end_trigger_punish_with_cooldown():
    e = encounter()
    e.boss.active = True
    e.bus.publish(ItemUseStartedEvent(e.player.id, "estus"))
    e.boss.tick(e.world)
    assert e.world.get(e.entity, AttackIntent).definition.kind == AttackKind.BACKSTEP_PUNISH
    assert e.boss.punish_cooldown == 180
    e = encounter()
    e.boss.active = True
    e.fighter.attack = Attack(e.profile.moveset(1)[0])
    for move in LONGSWORD_SPEC.attacks[:2]:
        e.hero.attack = Attack(move)
        e.boss.tick(e.world)
    e.hero.attack, e.fighter.attack = None, None
    e.boss.tick(e.world)
    assert e.world.get(e.entity, AttackIntent).definition.kind == AttackKind.BACKSTEP_PUNISH


def test_phase2_stagger_opens_four_critical_hits_and_phase1_does_not():
    e = encounter()
    e.bus.publish(StaggerTriggered(e.entity.id, False))
    assert e.fighter.riposte_steps == 0
    e.boss.phase = 2
    e.bus.publish(StaggerTriggered(e.entity.id, False))
    assert (e.fighter.riposte_steps, e.fighter.riposte_hits_remaining) == (240, 4)
    e.fighter.riposte_steps, e.fighter.riposte_hits_remaining = 90, 1
    e.bus.publish(ParrySucceeded(e.player.id, e.entity.id))
    assert (e.fighter.riposte_steps, e.fighter.riposte_hits_remaining) == (240, 4)


def test_phase_transition_blocks_existing_poison_for90_steps_then_resumes_ticks():
    from vigilia.combat.status import StatusEffect
    e = encounter()
    e.boss.active = True
    e.fighter.hp = 1599
    e.fighter.status.active[StatusEffect.POISON] = 600
    e.bus.publish(HPChangedEvent(e.entity.id, 1600, 1599, 3200, "dot"))
    for _ in range(90):
        e.boss.tick(e.world)
        e.fighter.tick()
    assert e.fighter.hp == 1599
    e.boss.tick(e.world)
    e.fighter.tick()
    assert e.fighter.hp < 1599


def test_death_waits_exactly_240_steps_and_emits_once_even_after_rest():
    e, events = encounter(), []
    e.bus.subscribe(BossDefeatedEvent, events.append)
    e.fighter.hp = 0
    e.bus.publish(EntityDied(e.entity.id))
    e.boss.reset_on_rest()
    for _ in range(239):
        e.boss.tick(e.world)
    assert not events and not e.fighter.alive
    e.boss.tick(e.world)
    for _ in range(300):
        e.boss.tick(e.world)
    assert events == [BossDefeatedEvent(e.profile.id, 2400)]
    assert e.boss.to_snapshot({}).fighter is None


def test_hot_reload_restarts_live_encounter_and_rejects_new_identity(tmp_path):
    e = encounter()
    e.boss.start()
    path = tmp_path / "warden.toml"
    path.write_text(PROFILE_PATH.read_text(encoding="utf-8").replace("windup = 54", "windup = 48"), encoding="utf-8")
    profile = load_boss_profile(path, register=False)
    e.fighter.hp = 2100
    e.boss.reload_profile(profile)
    assert e.fighter.hp == 3200 and e.boss.intro_remaining == 180
    assert e.boss.profile.moveset(1)[0].windup == 48
    with pytest.raises(ValueError):
        e.boss.reload_profile(replace(profile, id="other"))
    load_boss_profile(PROFILE_PATH)
