"""Seleção de slot usa apenas cabeçalhos fornecidos pela consulta."""

from types import SimpleNamespace
from ui_fakes import BackendFake, ActionsFake
from vigilia.core.views import SlotView, UICommand, UICommandKind
from vigilia.ui.slot_select import SlotSelect


def test_empty_slots_are_disabled_and_occupied_slot_dispatches_load():
    backend, actions = BackendFake(), ActionsFake()
    rows = [SlotView(1), SlotView(2, "Vésper", 7, 3660, "patio_da_vigilia", "", True), SlotView(3)]
    screen = SlotSelect(backend, SimpleNamespace(slots=lambda: rows), actions)
    assert not screen.grid.buttons[0].enabled and screen.grid.buttons[screen.grid.index].key == "front.slot.2"
    assert "01:01" in backend.nodes["front.slot.2"]["text"]
    screen.confirm()
    assert actions.commands == [UICommand(UICommandKind.LOAD_SLOT, "2")]
