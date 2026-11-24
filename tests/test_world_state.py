"""Descanso e teleporte por eventos preservam flags persistentes."""

import pytest

from vigilia.core.events import BonfireRestedEvent, EventBus, SaveRequestedEvent, LevelUpRequestedEvent
from vigilia.core.mathx import Vec3
from vigilia.model.world_state import WorldState
from vigilia.world.bonfire import BonfireService, BONFIRES


def test_rest_changes_checkpoint_before_autosave_and_preserves_flags() -> None:
    state, bus = WorldState(), EventBus()
    state.opened_shortcuts.add("portao")
    state.defeated_bosses.add("abadessa")
    order = []
    bus.subscribe(BonfireRestedEvent, lambda event: order.append(("rest", state.last_bonfire)))
    bus.subscribe(SaveRequestedEvent, lambda event: order.append(("save", event.reason)))
    fires = BonfireService(state, bus)
    fires.rest(BONFIRES["patio_norte"].position)
    assert order == [("rest", "patio_norte"), ("save", "bonfire")]
    assert state.opened_shortcuts == {"portao"} and state.defeated_bosses == {"abadessa"}
    fires.travel(BONFIRES["patio_norte"].position)
    assert state.last_bonfire == "patio_sul"


def test_travel_requires_discovery_and_level_hook_requires_a_bonfire() -> None:
    state, bus = WorldState(), EventBus()
    service = BonfireService(state, bus)
    with pytest.raises(ValueError):
        service.travel(BONFIRES["patio_sul"].position)
    with pytest.raises(ValueError):
        service.request_level_up(Vec3(10, 10), "vigor")
    received = []
    bus.subscribe(LevelUpRequestedEvent, received.append)
    service.request_level_up(BONFIRES["patio_sul"].position, "vigor")
    assert received == [LevelUpRequestedEvent("patio_sul", "vigor")]


def test_shortcut_opening_requests_save_and_survives_world_round_trip(tmp_path):
    from dataclasses import replace
    from combat_fakes import PhysicsFake
    from test_save import full_snapshot
    from vigilia.save.service import SaveService
    from vigilia.world.shortcut import Shortcut, SHORTCUT_ID
    state, bus, obstacle, requests = WorldState(), EventBus(), PhysicsFake(), []
    door = Shortcut(Vec3(0, 8, 1), obstacle, state, bus)
    bus.subscribe(SaveRequestedEvent, requests.append)
    door.open(Vec3(0, 7, 1))
    assert SHORTCUT_ID in state.opened_shortcuts and not obstacle.active
    assert len(requests) == 1
    snapshot = full_snapshot()
    snapshot = replace(snapshot, world=replace(snapshot.world,
        opened_shortcuts=tuple(state.opened_shortcuts), boss_phases={"warden_of_the_forge": 2}))
    service = SaveService(tmp_path / "world.sqlite3")
    service.save(1, snapshot)
    loaded = service.load()
    assert loaded.world.opened_shortcuts == (SHORTCUT_ID,)
    assert loaded.world.boss_phases == {"warden_of_the_forge": 2}
    assert loaded.world.visited_bonfires == snapshot.world.visited_bonfires
    assert loaded.world.defeated_bosses == snapshot.world.defeated_bosses
