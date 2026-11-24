"""Categorias, comparação de dano e comandos de equipamento sem imports de modelo."""

from ui_fakes import BackendFake, QueryFake, ActionsFake
from vigilia.core.views import ItemCategory, UICommand, UICommandKind
from vigilia.ui.inventory_ui import InventoryUI
from vigilia.ui.widgets import Panel


def inventory():
    backend, query, actions = BackendFake(), QueryFake(), ActionsFake()
    Panel(backend, "menu", (0, 0, 1280, 720))
    return InventoryUI(backend, query, actions), backend, query, actions


def test_inventory_selection_compares_damage_scaling_and_equips_selected_weapon():
    menu, backend, query, actions = inventory()
    menu.move(dx=1)
    text = backend.nodes["menu.inventory.compare"]["text"]
    assert "40.1" in text and "+7.9" in text and "S / E" in text
    menu.confirm()
    assert actions.commands == [UICommand(UICommandKind.EQUIP, "axe")]


def test_category_changes_remove_previous_items_and_empty_categories_are_safe():
    menu, backend, query, actions = inventory()
    menu.change_category(1)
    assert len(menu.items) == 2 and menu.category == ItemCategory.WEAPON
    menu.change_category(1)
    assert not menu.items
    menu.confirm()
    assert not actions.commands and "menu.inventory.empty" in backend.nodes
    menu.change_category(1)
    assert menu.items[0].id == "shard"
    menu.confirm()
    assert not actions.commands
