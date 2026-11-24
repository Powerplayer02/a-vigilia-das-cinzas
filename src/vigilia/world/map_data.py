"""Provedor de descoberta e posição para a futura interface de mapa."""

from vigilia.core.events import EventBus, AreaEnteredEvent
from vigilia.core.mathx import Transform, Vec3
from vigilia.entities.ecs import World
from vigilia.model.world_state import WorldState
from vigilia.core.views import MapRegionView, MapMarkerView
from vigilia.world.bonfire import BONFIRES

from vigilia.model.areas import AREA_BOUNDS, area_at

AREA_IDS = tuple(AREA_BOUNDS)


class MapDataProvider:
    def __init__(self, state: WorldState, player: Transform, bus: EventBus) -> None:
        self.state, self.player, self._bus = state, player, bus
        self._last_area = None
        bus.subscribe(AreaEnteredEvent, self._discover)

    def _discover(self, event: AreaEnteredEvent) -> None:
        if event.area_id in AREA_IDS:
            self.state.discovered_areas.add(event.area_id)
            self._last_area = event.area_id

    def discovered_areas(self) -> tuple[str, ...]:
        return tuple(area for area in AREA_IDS if area in self.state.discovered_areas)

    def discovered_bonfires(self) -> tuple[str, ...]:
        return self.state.bonfires_discovered if "patio_da_vigilia" in self.state.discovered_areas else ()

    def player_position(self) -> Vec3:
        return self.player.position

    def regions(self) -> tuple[MapRegionView, ...]:
        bounds = AREA_BOUNDS
        return tuple(MapRegionView(key, bounds[key]) for key in self.discovered_areas())

    def bonfires(self) -> tuple[MapMarkerView, ...]:
        return tuple(MapMarkerView(key, BONFIRES[key].position) for key in self.discovered_bonfires())

    def tick(self, world: World) -> None:
        area = area_at(self.player.position)
        if area != self._last_area:
            self._bus.publish(AreaEnteredEvent(area))
