"""Previsão, foco e custo respeitam o contrato de stats."""

from dataclasses import replace

from ui_fakes import BackendFake, QueryFake, ActionsFake
from vigilia.core.views import UICommand, UICommandKind
from vigilia.ui.level_up_ui import LevelUpUI
from vigilia.ui.widgets import Panel


def level_menu():
    backend, query, actions = BackendFake(), QueryFake(), ActionsFake()
    Panel(backend, "menu", (0, 0, 1280, 720))
    return LevelUpUI(backend, query, actions), backend, query, actions


def test_level_ui_previews_hp_and_dispatches_selected_stat():
    menu, backend, query, actions = level_menu()
    assert "140 -> 146" in menu.preview_label.value
    menu.confirm()
    assert actions.commands == [UICommand(UICommandKind.LEVEL_UP, "vigor")]
    menu.move(dy=1)
    menu.confirm()
    assert actions.commands[-1].argument == "endurance"


def test_insufficient_souls_or_missing_bonfire_disable_buttons():
    menu, backend, query, actions = level_menu()
    query.stats = replace(query.stats, souls=0)
    menu.refresh()
    menu.confirm()
    assert not actions.commands and not menu.grid.buttons[0].enabled
    query.stats = replace(query.stats, souls=500, can_level=False)
    menu.refresh()
    assert not any(button.enabled for button in menu.grid.buttons)
