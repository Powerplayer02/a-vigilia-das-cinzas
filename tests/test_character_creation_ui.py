"""Rascunho, destino vazio e confirmação da criação por contrato."""

import json
from types import SimpleNamespace
from ui_fakes import BackendFake, ActionsFake
from vigilia.core.views import CharacterClassView, StatView, SlotView, UICommandKind
from vigilia.ui.character_creation import CharacterCreation


def test_creation_preserves_name_and_only_confirms_after_ten_points():
    backend, actions = BackendFake(), ActionsFake()
    stats = tuple(StatView(key, key, 10) for key in ("vigor", "endurance", "strength", "dexterity", "intelligence", "faith", "luck"))
    profiles = tuple(CharacterClassView(key, key, "", "Espada", stats) for key in ("warrior", "knight", "assassin", "mage", "cleric"))
    query = SimpleNamespace(character_classes=lambda: profiles, slots=lambda: [SlotView(1, occupied=True), SlotView(2), SlotView(3)])
    screen = CharacterCreation(backend, query, actions)
    assert screen.slot == 2
    screen.create()
    assert not actions.commands
    backend.text("front.name", "Vésper")
    screen.select_class(3)
    assert screen.entry.value == "Vésper"
    screen.adjust("vigor", 20)
    assert screen.remaining == 0 and screen.allocation["vigor"] == 10
    screen.create()
    command = actions.commands[-1]
    assert command.kind == UICommandKind.CREATE_CHARACTER
    data = json.loads(command.argument)
    assert data["slot"] == 2 and data["name"] == "Vésper" and data["class_id"] == "mage"
