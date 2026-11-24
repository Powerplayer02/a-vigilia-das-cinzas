"""Revisão e confirmação da escolha final usando somente comandos da UI."""

from vigilia.core.views import UICommand, UICommandKind
from vigilia.ui.widgets import Panel, Label, Button, Grid
from vigilia.ui.text_render import TITLE, GOLD, MUTED


class EndingUI:
    def __init__(self, backend, actions):
        self.backend, self.actions = backend, actions
        self.pending, self.index, self.root = "", 0, None
        self.refresh()

    def refresh(self, error=""):
        if self.root:
            self.root.destroy()
        b = self.backend
        self.root = Panel(b, "menu.ending", (410, 138, 672, 466), parent="menu")
        Label(b, "menu.ending.title", b.t("ending.title"), (18, 8, 630, 50), parent=self.root.key, size=TITLE, color=GOLD)
        if self.pending:
            Label(b, "menu.ending.review", b.t("ending." + self.pending + ".epilogue"), (18, 78, 630, 170), parent=self.root.key)
            Label(b, "menu.ending.warning", error or b.t("ending.confirm"), (18, 258, 620, 68), parent=self.root.key, color=MUTED)
            self.grid = Grid([
                Button(b, "menu.ending.cancel", b.t("common.cancel"), (18, 356, 270, 48), self.cancel, parent=self.root.key),
                Button(b, "menu.ending.accept", b.t("ending.commit"), (316, 356, 320, 48), self.commit, parent=self.root.key)])
        else:
            self.grid = Grid([Button(b, "menu.ending." + choice, b.t("ending." + choice + ".name"),
                (18, 76 + i*68, 620, 52), lambda choice=choice: self.review(choice), parent=self.root.key)
                for i, choice in enumerate(("maintain", "extinguish", "transform"))])
            self.grid.select(self.index)
            Label(b, "menu.ending.help", b.t("ending.help"), (18, 310, 620, 120), parent=self.root.key, color=MUTED)

    def review(self, choice):
        self.index, self.pending = self.grid.index, choice
        self.refresh()

    def cancel(self):
        self.pending = ""
        self.refresh()

    def back(self):
        if self.pending:
            self.cancel()
            return True
        return False

    def commit(self):
        error = self.actions.execute(UICommand(UICommandKind.CHOOSE_ENDING, self.pending))
        if error:
            self.refresh(error)

    def move(self, dx=0, dy=0):
        self.grid.move(dx, dy)

    def confirm(self):
        self.grid.confirm()
