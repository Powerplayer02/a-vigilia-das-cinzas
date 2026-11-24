"""Fases finais, telegraph/pulsos, snapshot e decisões irreversíveis."""

from dataclasses import replace
from pathlib import Path
import pytest

from boss_fakes import encounter
from combat_fakes import ContactFake, PhysicsFake
from vigilia.ai.bosses import PhaseTransitionEvent
from vigilia.combat.events import HPChangedEvent, DamageDealt
from vigilia.combat.orchestrator import CombatSystem
from vigilia.core.mathx import Transform, Vec3
from vigilia.model.bosses import load_boss_profile
from vigilia.model.endings import choose_ending, ENDINGS, FINAL_BOSS
from vigilia.model.world_state import WorldState
from vigilia.save.serializers import encode, decode, SaveFormatError
from vigilia.world.area import load_area
from test_save import full_snapshot

ROOT = Path(__file__).parents[1]


def final_encounter():
    e = encounter()
    profile = load_boss_profile(ROOT / "data/bosses/custodian.toml")
    e.boss.profile, e.profile = profile, profile
    e.fighter.stats, e.fighter.weapon = profile.stats, profile.weapon.instantiate()
    e.fighter.restore()
    return e


def test_third_phase_thresholds_cancel_attack_and_persist_hazard_clock():
    e, phases = final_encounter(), []
    e.bus.subscribe(PhaseTransitionEvent, phases.append)
    e.boss.start()
    for fraction, expected in ((.66, 1), (.659, 2), (.33, 2), (.329, 3)):
        e.fighter.hp = e.profile.max_hp * fraction
        e.bus.publish(HPChangedEvent(e.entity.id, 5600, e.fighter.hp, 5600, "player"))
        assert e.boss.phase == expected
    assert [event.phase for event in phases] == [2, 3]
    assert e.boss.transition_remaining == 90 and e.fighter.invulnerable
    e.boss.hazard_step = 121
    snapshot = e.boss.to_snapshot({e.entity.id: e.profile.id, e.player.id: "player"})
    e.boss.hazard_step = 0
    e.boss.from_snapshot(snapshot, {e.profile.id: e.entity.id, "player": e.player.id}, False)
    assert (e.boss.phase, e.boss.hazard_step) == (3, 121)


def test_vents_warn_for_90_steps_then_pulse_three_times_and_stop_on_death():
    e, pulses = final_encounter(), []
    e.boss.phase, e.boss.active = 3, True
    e.boss.hazard_sink = lambda *args: pulses.append(args)
    for _ in range(89):
        e.boss.tick(e.world)
    assert not pulses and e.boss.hazard_visible
    for _ in range(41):
        e.boss.tick(e.world)
    assert len(pulses) == 3
    assert all(pulse[2] == 2.4 for pulse in pulses)
    e.fighter.hp = 0
    for _ in range(400):
        e.boss.tick(e.world)
    assert len(pulses) == 3 and not e.boss.hazard_visible


def test_environment_respects_current_iframes_and_resistance_and_does_not_repeat():
    e, events = final_encounter(), []
    resolver = CombatSystem(ContactFake(), PhysicsFake(), e.bus)
    pose = e.world.get(e.player, Transform)
    e.bus.subscribe(DamageDealt, events.append)
    e.hero.invulnerable = True
    resolver.queue_hazard(e.entity.id, pose.position, 2.4)
    resolver.resolve(e.world)
    assert not events
    e.hero.invulnerable = False
    resolver.queue_hazard(e.entity.id, pose.position, 2.4)
    before = e.hero.hp
    resolver.resolve(e.world)
    assert len(events) == 1 and 0 < before - e.hero.hp < 28
    resolver.resolve(e.world)
    assert len(events) == 1


@pytest.mark.parametrize("choice", ENDINGS)
def test_ending_requires_victory_roundtrips_and_cannot_be_replaced(choice):
    state = WorldState()
    with pytest.raises(ValueError):
        choose_ending(state, choice)
    state.defeated_bosses.add(FINAL_BOSS)
    choose_ending(state, choice)
    choose_ending(state, choice)
    with pytest.raises(ValueError):
        choose_ending(state, next(other for other in ENDINGS if other != choice))
    original = full_snapshot()
    snapshot = replace(original, world=replace(original.world, ending=choice, credits_seen=True,
        defeated_bosses=tuple(sorted(set(original.world.defeated_bosses) | {FINAL_BOSS}))))
    assert decode(snapshot.version, snapshot.timing_version, *encode(snapshot)) == snapshot
    with pytest.raises(SaveFormatError):
        encode(replace(snapshot, world=replace(snapshot.world, defeated_bosses=())))


def test_both_new_areas_have_reachable_exit_fire_and_boss_gating():
    for name in ("ruinas_subterraneas", "forno_da_vigilia"):
        area = load_area(ROOT / "data/areas" / (name + ".toml"))
        grid = area.navigation(fog_closed=False)
        from vigilia.ai.pathfinding import a_star
        for passage in area.passages:
            assert a_star(grid, area.spawn, passage.position)
    marsh = load_area(ROOT / "data/areas/pantano_das_cinzas.toml")
    gate = next(p for p in marsh.passages if p.target == "ruinas_subterraneas")
    assert gate.requires_boss == "abbess_of_the_tide" and gate.arrival == Vec3(180, -10, 1.02)


def test_furnace_arena_cannot_be_reached_around_the_closed_fog():
    from vigilia.ai.pathfinding import a_star
    area = load_area(ROOT / "data/areas/forno_da_vigilia.toml")
    destination = Vec3(*area.boss["spawn"])
    assert not a_star(area.navigation(fog_closed=True), area.spawn, destination)
    assert a_star(area.navigation(fog_closed=False), area.spawn, destination)


def test_failed_ending_commit_rolls_back_choice_and_allows_retry():
    from types import SimpleNamespace
    from vigilia.game import Game
    from vigilia.core.types import AppState
    game = Game.__new__(Game)
    game.active_area, game.active_slot = "forno_da_vigilia", 1
    game._transform = Transform(Vec3(240,35,1.02))
    transitions = []
    game.flow = SimpleNamespace(current=AppState.PAUSED, transition=transitions.append)
    game.world_state = WorldState(defeated_bosses={FINAL_BOSS})
    game._bus = SimpleNamespace(publish=lambda event: setattr(game, "_pending_save", event))
    game._flush_save = lambda: None
    with pytest.raises(ValueError, match="ending.save_failed"):
        game._choose_ending("maintain")
    assert game.world_state.ending == "" and transitions == []
    game._flush_save = lambda: setattr(game, "_pending_save", None)
    game._choose_ending("transform")
    assert game.world_state.ending == "transform" and transitions == [AppState.CREDITS]


def test_credit_back_error_stays_visible_and_is_not_dispatched_twice():
    from types import SimpleNamespace
    from ui_fakes import BackendFake
    from vigilia.ui.main_menu import Credits
    calls = []
    def fail(command):
        calls.append(command)
        return "Falha ao salvar"
    backend = BackendFake()
    credits = Credits(backend, SimpleNamespace(ending=lambda: "transform"), SimpleNamespace(execute=fail))
    assert credits.back()
    assert len(calls) == 1 and backend.nodes["front.error"]["text"] == "Falha ao salvar"

