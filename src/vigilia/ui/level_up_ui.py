"""Seleção de atributo e previsão numérica antes de gastar almas."""

from vigilia.core.protocols import IStatsQuery, IUIActions
from vigilia.core.views import UICommand, UICommandKind
from vigilia.ui.widgets import Label, Button, Grid, Panel
from vigilia.ui.text_render import TITLE, SECONDARY, GOLD, MUTED


class LevelUpUI:
    def __init__(self, backend, query: IStatsQuery, actions: IUIActions):
        self.backend, self.query, self.actions = backend, query, actions
        self.root = Panel(backend, "menu.level", (410, 138, 672, 466), parent="menu", color=(0, 0, 0, 0))
        self.body = None
        self.index = 0
        self.refresh()

    def refresh(self, message=""):
        if self.body is not None:
            self.body.destroy()
        self.body = Panel(self.backend, "menu.level.body", (0, 0, 672, 466), parent=self.root.key, color=(0, 0, 0, 0))
        self.view = self.query.current()
        cost = self.query.next_level_cost()
        Label(self.backend, "menu.level.title", self.backend.t("level.title", level=self.view.level), (14, 0, 632, 38), parent=self.body.key, size=TITLE, color=GOLD)
        Label(self.backend, "menu.level.cost", self.backend.t("level.cost", souls=self.view.souls, cost=cost), (14, 48, 632, 30), parent=self.body.key)
        buttons = []
        for index, stat in enumerate(self.view.attributes):
            button = Button(self.backend, f"menu.level.{stat.id}", f"{index + 2}   {stat.name}   {stat.value} -> {min(99, stat.value + 1)}",
                (14, 96 + index * 42, 286, 36), lambda index=index: self.apply_index(index), parent=self.body.key, size=SECONDARY)
            button.enable(self.view.can_level and self.view.souls >= cost and stat.value < 99)
            buttons.append(button)
        self.grid = Grid(buttons)
        self.grid.select(self.index)
        self.preview_label = Label(self.backend, "menu.level.preview", "", (334, 96, 304, 190), parent=self.body.key)
        help_text = message or self.backend.t("level.help" if self.view.can_level else "level.bonfire")
        if not message and self.view.can_level and self.view.souls < cost:
            help_text = self.backend.t("level.insufficient")
        Label(self.backend, "menu.level.message", help_text, (334, 306, 304, 120), parent=self.body.key, size=SECONDARY, color=MUTED)
        self.preview()

    def preview(self):
        self.index = self.grid.index
        stat = self.view.attributes[self.index]
        after = self.query.preview(stat.id)
        self.preview_label.set(self.backend.t("level.preview", name=stat.name.upper(), hp=f"{self.view.max_hp:.0f}", next_hp=f"{after.max_hp:.0f}",
            stamina=f"{self.view.max_stamina:.0f}", next_stamina=f"{after.max_stamina:.0f}", capacity=f"{self.view.capacity:.0f}",
            next_capacity=f"{after.capacity:.0f}", poise=f"{self.view.poise:.0f}", next_poise=f"{after.poise:.0f}"))

    def move(self, dx=0, dy=0):
        self.grid.move(dx, dy)
        self.preview()

    def apply_index(self, index):
        self.index = index
        message = self.actions.execute(UICommand(UICommandKind.LEVEL_UP, self.view.attributes[index].id))
        self.refresh(message)

    def confirm(self):
        self.grid.confirm()
