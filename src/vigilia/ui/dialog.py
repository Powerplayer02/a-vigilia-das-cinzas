"""Modal compartilhado: Cancelar é sempre o foco inicial."""

from vigilia.ui.widgets import Panel, Label, Button, Grid
from vigilia.ui.text_render import GOLD, SECONDARY


class Dialog:
    def __init__(self, backend, title, body, accept, cancel, *, accept_label="common.confirm", danger=False):
        self.backend, self.body, self.title_key, self.accept_label = backend, body, title, accept_label
        self.root = Panel(backend, "front.modal", (0, 0, 1280, 720), parent="front", color=(0, 0, 0, .82))
        Panel(backend, "front.modal.box", (244, 190, 792, 358), parent=self.root.key)
        self.title = Label(backend, "front.modal.title", "", (274, 210, 730, 48), parent=self.root.key, color=GOLD)
        self.text = Label(backend, "front.modal.body", "", (274, 272, 730, 172), parent=self.root.key, size=SECONDARY)
        self.cancel_button = Button(backend, "front.modal.cancel", backend.t("common.cancel"), (274, 476, 338, 44), cancel, parent=self.root.key)
        self.accept_button = Button(backend, "front.modal.accept", backend.t(accept_label), (642, 476, 362, 44), accept, parent=self.root.key, danger=danger)
        self.grid = Grid([self.cancel_button, self.accept_button])
        self.grid.select(0)
        self.refresh()

    def refresh(self):
        self.title.set(self.backend.t(self.title_key))
        self.text.set(self.body() if callable(self.body) else self.body)
        self.backend.text(self.cancel_button.key, self.backend.t("common.cancel"))
        self.backend.text(self.accept_button.key, self.backend.t(self.accept_label))

    def move(self, dx=0, dy=0):
        self.grid.move(dx, dy)

    def confirm(self):
        self.grid.confirm()
