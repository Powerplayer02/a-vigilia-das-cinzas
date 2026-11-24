"""Entrada do jogo e créditos, com dados lidos por protocolos."""

from vigilia.core.views import UICommand, UICommandKind as C
from vigilia.ui.widgets import Panel, Label, Button, Grid
from vigilia.ui.text_render import GOLD, MUTED, SECONDARY, TITLE, BOSS_NAME


def sheet(backend, title):
    root = Panel(backend, "front", (0, 0, 1280, 720), color=(.012, .018, .025, .65))
    Panel(backend, "front.sheet", (136, 36, 1008, 648), parent="front")
    Panel(backend, "front.line", (136, 36, 1008, 3), parent="front", color=GOLD)
    Label(backend, "front.title", backend.t(title), (164, 60, 920, 56), parent="front", size=TITLE, color=GOLD)
    Label(backend, "front.hint", backend.t("common.menu_hint"), (164, 642, 920, 28), parent="front", size=SECONDARY, color=MUTED)
    return root


class MainMenu:
    def __init__(self, backend, query, actions):
        self.root = Panel(backend, "front", (0, 0, 1280, 720), color=(.012, .018, .025, .38))
        Label(backend, "front.title", backend.t("game.title"), (80, 84, 1120, 72), parent="front", size=BOSS_NAME, color=GOLD)
        Label(backend, "front.subtitle", backend.t("game.subtitle"), (84, 168, 1000, 40), parent="front")
        Panel(backend, "front.line", (84, 220, 400, 2), parent="front", color=GOLD)
        entries = (("main.new", C.NEW_GAME), ("main.continue", C.CONTINUE), ("main.options", C.OPEN_OPTIONS),
                   ("main.credits", C.OPEN_CREDITS), ("main.quit", C.QUIT))
        self.buttons = [Button(backend, f"front.action.{command.value}", backend.t(key), (84, 252 + i * 65, 400, 52),
                               lambda command=command: actions.execute(UICommand(command)), parent="front")
                        for i, (key, command) in enumerate(entries)]
        slots = query.slots()
        self.buttons[0].enable(any(not slot.occupied for slot in slots))
        self.buttons[1].enable(any(slot.occupied for slot in slots))
        Label(backend, "front.hint", backend.t("common.menu_hint"), (84, 640, 1100, 34), parent="front", size=SECONDARY, color=MUTED)
        self.grid = Grid(self.buttons)
        self.grid.select(next(i for i, button in enumerate(self.buttons) if button.enabled))

    def move(self, dx=0, dy=0):
        self.grid.move(dx, dy)

    def confirm(self):
        self.grid.confirm()


class Credits:
    def __init__(self, backend, query, actions):
        self.backend, self.actions = backend, actions
        self.root = sheet(backend, "credits.title")
        Label(backend, "front.body", backend.t("credits.body"), (180, 154, 900, 370), parent="front")
        if hasattr(query, "ending") and query.ending():
            backend.text("front.body", backend.t("ending." + query.ending() + ".epilogue") + "\n\n" + backend.t("credits.body"))
        self.grid = Grid([Button(backend, "front.back", backend.t("common.back"), (180, 560, 260, 48),
                         self.back, parent="front")])
        self.error = Label(backend, "front.error", "", (180, 612, 890, 28), parent="front")

    def move(self, dx=0, dy=0):
        self.grid.move(dx, dy)

    def confirm(self):
        self.grid.confirm()

    def back(self):
        error = self.actions.execute(UICommand(C.BACK))
        if error:
            self.error.set(error)
        return True
