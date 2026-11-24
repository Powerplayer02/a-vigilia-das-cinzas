"""Contrato de mapa fornece descoberta e posição sem depender da interface."""

from vigilia.core.events import EventBus, AreaEnteredEvent
from vigilia.core.mathx import Transform, Vec3
from vigilia.core.protocols import IMapDataProvider
from vigilia.entities.ecs import World
from vigilia.model.world_state import WorldState
from vigilia.world.bonfire import BonfireService, BONFIRES
from vigilia.world.map_data import MapDataProvider


def test_fresh_map_returns_empty_discovery_until_entry_event():
    bus, state = EventBus(), WorldState()
    data = MapDataProvider(state, Transform(), bus)
    assert isinstance(data, IMapDataProvider)
    assert data.discovered_areas() == data.discovered_bonfires() == ()
    bus.publish(AreaEnteredEvent("patio_da_vigilia"))
    assert data.discovered_areas() == ("patio_da_vigilia",)
    assert data.discovered_bonfires() == ("patio_sul",)


def test_lighting_a_bonfire_updates_provider_without_ui():
    bus, state = EventBus(), WorldState()
    data = MapDataProvider(state, Transform(), bus)
    bus.publish(AreaEnteredEvent("patio_da_vigilia"))
    BonfireService(state, bus).rest(BONFIRES["patio_norte"].position)
    assert set(data.discovered_bonfires()) == {"patio_sul", "patio_norte"}


def test_provider_tracks_player_and_emits_area_change_once():
    bus, pose, events = EventBus(), Transform(Vec3(1, 2, 1)), []
    data = MapDataProvider(WorldState(), pose, bus)
    bus.subscribe(AreaEnteredEvent, events.append)
    data.tick(World())
    data.tick(World())
    pose.position = Vec3(3, 20, 1)
    data.tick(World())
    assert data.player_position() == Vec3(3, 20, 1)
    assert len(events) == 2 and "forge_arena" in data.discovered_areas()
