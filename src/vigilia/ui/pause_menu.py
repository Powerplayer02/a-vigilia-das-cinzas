"""Estrutura de pausa e navegação por foco."""

from collections.abc import Callable
from vigilia.core.palette import PALETTE

from vigilia.ui.widgets import Panel, Label, Button, Grid, Sprite
from vigilia.ui.text_render import TITLE, SECONDARY, GOLD, MUTED

PAGES = (("status", "pause.status"), ("inventory", "pause.inventory"), ("equipment", "pause.equipment"),
         ("level", "pause.level"), ("map", "pause.map"), ("options", "pause.options"), ("resume", "pause.resume"),
         ("main", "pause.main"))


class PauseMenu:
    def __init__(self, backend, open_page: Callable[[str], None], title=None):
        self.root = Panel(backend, "menu", (0, 0, 1280, 720), color=PALETTE["veil"])
        Panel(backend, "menu.sheet", (166, 52, 948, 616), parent="menu")
        Panel(backend, "menu.edge", (166, 52, 948, 3), parent="menu", color=GOLD)
        Sprite(backend, "menu.seal", "ember", (1030, 70, 52, 52), parent="menu")
        Label(backend, "menu.title", title or backend.t("pause.title"), (194, 75, 850, 42), parent="menu", size=TITLE, color=GOLD)
        Label(backend, "menu.hint", backend.t("common.menu_hint"),
              (194, 621, 884, 24), parent="menu", size=SECONDARY, color=MUTED)
        self.buttons = [Button(backend, f"menu.nav.{page}", backend.t(name), (194, 140 + index * 56, 206, 48),
                               lambda page=page: open_page(page), parent="menu",
                               icon={"status":"helm","inventory":"shard","equipment":"sword","level":"levels","map":"map","options":"settings","resume":"back","main":"exit"}[page])
                        for index, (page, name) in enumerate(PAGES)]
        self.grid = Grid(self.buttons)
