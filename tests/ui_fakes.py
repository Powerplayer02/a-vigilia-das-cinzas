"""Adaptadores de apresentação sem janela e dados independentes do domínio."""

from dataclasses import replace
from pathlib import Path
from vigilia.core.locale import Localizer

from vigilia.core.views import VitalsView, BossView, StatusView, StatsView, StatView, ItemView, EquipmentView, ItemCategory


class BackendFake:
    def __init__(self):
        self.nodes, self.updates = {}, []
        self.localizer = Localizer(Path(__file__).resolve().parents[1] / "data/locale")

    def t(self, key, **values):
        return self.localizer.t(key, **values)

    def read_text(self, key):
        return self.nodes[key].get("text", "")

    def focus_text(self, key, value):
        self.nodes[key]["focus"] = value

    def text_active(self):
        return any(node.get("focus", False) for node in self.nodes.values())

    def create(self, key, kind, rect, **properties):
        assert key not in self.nodes
        self.nodes[key] = dict(kind=kind, rect=rect, visible=True, **properties)

    def text(self, key, value):
        self.nodes[key]["text"] = value
        self.updates.append(("text", key, value))

    def visible(self, key, value):
        self.nodes[key]["visible"] = value

    def fraction(self, key, value):
        self.nodes[key]["fraction"] = value
        self.updates.append(("fraction", key, value))

    def color(self, key, value):
        self.nodes[key]["color"] = value

    def enabled(self, key, value):
        self.nodes[key]["enabled"] = value

    def destroy(self, key):
        for child in [name for name, node in self.nodes.items() if node.get("parent") == key]:
            self.destroy(child)
        del self.nodes[key]


class QueryFake:
    def __init__(self):
        self.vitals = VitalsView(140, 140, 110, 110, 500, "Espada longa +0")
        self.boss = None
        self.statuses = []
        self.stats = StatsView(1, 500, tuple(StatView(key, name, 10) for key, name in (
            ("vigor", "Vigor"), ("endurance", "Endurance"), ("strength", "Força"), ("dexterity", "Destreza"),
            ("intelligence", "Inteligência"), ("faith", "Fé"), ("luck", "Sorte"))),
            140, 110, 40, 25.8, 44, "Médio", (("Corte", 6),), True)
        self.items = [ItemView("longsword", "Espada longa", ItemCategory.WEAPON, 1, 4.8, 32.2, "B / C", "8 / 8", True, True),
                      ItemView("axe", "Machado", ItemCategory.WEAPON, 1, 6.8, 40.1, "S / E", "10 / 5", False, True),
                      ItemView("shard", "Fragmento", ItemCategory.MATERIAL, 3, .1, description="Melhora armas.")]

    def player_vitals(self):
        return self.vitals

    def active_boss(self):
        return self.boss

    def active_statuses(self):
        return self.statuses

    def current(self):
        return self.stats

    def preview(self, attribute):
        return replace(self.stats, max_hp=146 if attribute == "vigor" else 140)

    def next_level_cost(self):
        return 88

    def items_by_category(self, category):
        return [item for item in self.items if category == ItemCategory.ALL or item.category == category]

    def equipped(self):
        return EquipmentView(next(item for item in self.items if item.equipped), (), 25.8, 44)


class ActionsFake:
    def __init__(self):
        self.commands = []

    def execute(self, command):
        self.commands.append(command)
        return "Comando recebido."
