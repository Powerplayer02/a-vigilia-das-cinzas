"""Foco nas regiões descobertas sem acesso da UI a serviços de mundo."""

from types import SimpleNamespace
from ui_fakes import BackendFake
from vigilia.core.mathx import Vec3
from vigilia.core.views import MapRegionView, MapMarkerView
from vigilia.ui.map_view import MapView
from vigilia.ui.widgets import Panel


def test_empty_map_reveals_regions_bonfires_and_updates_player_marker():
    backend = BackendFake()
    Panel(backend, "menu", (0, 0, 1280, 720))
    state = SimpleNamespace(areas=(), markers=(), position=Vec3())
    query = SimpleNamespace(regions=lambda: state.areas,
        discovered_areas=lambda: tuple(r.id for r in state.areas),
        discovered_bonfires=lambda: tuple(f.id for f in state.markers),
        player_position=lambda: state.position, bonfires=lambda: state.markers)
    view = MapView(backend, query)
    assert "menu.map.empty" in backend.nodes and "menu.map.player" not in backend.nodes
    state.areas = (MapRegionView("patio_da_vigilia", (-12,-14,24,28)),)
    state.markers = (MapMarkerView("patio_sul", Vec3(0,-6,0)),)
    view.tick()
    assert "menu.map.empty" not in backend.nodes
    assert "menu.map.bonfire.patio_sul" in backend.nodes
    before = backend.nodes["menu.map.player"]["rect"]
    state.position = Vec3(3, 0, 0)
    view.tick()
    assert backend.nodes["menu.map.player"]["rect"][0] > before[0]


def test_map_selects_player_region_and_navigates_without_undiscovered_regions():
    backend = BackendFake()
    Panel(backend, "menu", (0, 0, 1280, 720))
    regions = (MapRegionView("patio_da_vigilia", (-12,-14,24,28)),
               MapRegionView("catedral_submersa", (46,-16,28,40)),
               MapRegionView("pantano_das_cinzas", (106,-16,28,56)))
    query = SimpleNamespace(regions=lambda: regions, discovered_areas=lambda: tuple(r.id for r in regions),
        discovered_bonfires=lambda: ("patio_sul",), player_position=lambda: Vec3(120,-10,1),
        bonfires=lambda: (MapMarkerView("patio_sul", Vec3(0,-6,0)),))
    view = MapView(backend, query)
    assert view.selection == 2
    view.confirm()
    assert view.focused and "menu.map.region.pantano_das_cinzas" in backend.nodes
    assert "menu.map.region.patio_da_vigilia" not in backend.nodes
    view.move(1, 0)
    assert view.selection == 0 and "menu.map.region.patio_da_vigilia" in backend.nodes
    assert not backend.nodes["menu.map.player"]["visible"]
    view.move(0, 1)
    assert not view.focused and all("menu.map.region." + r.id in backend.nodes for r in regions)
