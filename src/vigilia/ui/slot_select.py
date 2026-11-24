"""TrÃªs cabeÃ§alhos e exclusÃ£o com duas confirmaÃ§Ãµes, por consultas/aÃ§Ãµes."""

import json
from vigilia.core.views import UICommand, UICommandKind as C
from vigilia.ui.main_menu import sheet
from vigilia.ui.widgets import Label, Button, Grid
from vigilia.ui.dialog import Dialog
from vigilia.ui.text_render import GOLD, SECONDARY


class SlotSelect:
    def __init__(self, backend, query, actions, *, empty_only=False):
        self.backend, self.query, self.actions, self.empty_only = backend, query, actions, empty_only
        self.root = sheet(backend, "slots.new_title" if empty_only else "slots.title")
        self.message = Label(backend, "front.message", "", (180, 536, 880, 40), parent="front", size=SECONDARY, color=GOLD)
        self.modal, self.info, self.stage, self.wait = None, None, 0, 0.
        self.language = backend.t("locale.id")
        self.slot_buttons, self.delete_buttons, buttons = [], [], []
        for slot in (1, 2, 3):
            load = Button(backend, f"front.slot.{slot}", "", (180, 144 + (slot - 1) * 126, 748, 104),
                lambda slot=slot: self.choose(slot), parent="front")
            delete = Button(backend, f"front.delete.{slot}", backend.t("slots.delete"), (946, 166 + (slot - 1) * 126, 114, 56),
                lambda slot=slot: self.request_delete(slot), parent="front", size=SECONDARY, danger=True)
            self.slot_buttons.append(load)
            self.delete_buttons.append(delete)
            buttons.extend((load, delete))
        buttons.append(Button(backend, "front.options", backend.t("main.options"), (180, 582, 400, 44),
            lambda: self.options(), parent="front"))
        buttons.append(Button(backend, "front.back", backend.t("common.back"), (620, 582, 440, 44),
            lambda: actions.execute(UICommand(C.BACK)) if self.modal is None else None, parent="front"))
        self.grid = Grid(buttons, 2)
        self.refresh()
        self.grid.select(next((i * 2 for i, button in enumerate(self.slot_buttons) if button.enabled), len(buttons) - 1))

    def refresh(self):
        self.rows = self.query.slots()
        for row, button, delete in zip(self.rows, self.slot_buttons, self.delete_buttons):
            seconds = int(row.playtime_sec)
            class_name = self.backend.t("class." + row.class_id + ".name") if row.class_id else self.backend.t("slots.legacy_class")
            text = self.backend.t("slots.profile", slot=row.slot, name=row.name, level=row.level, class_name=class_name,
                time=f"{seconds // 3600:02}:{seconds % 3600 // 60:02}", area=self.backend.t("area." + row.area_id)) if row.occupied else self.backend.t("slots.empty", slot=row.slot)
            self.backend.text(button.key, text)
            button.enable(not row.occupied if self.empty_only else row.occupied)
            delete.enable(row.occupied)
            self.backend.text(delete.key, self.backend.t("slots.delete"))
        self.backend.text("front.title", self.backend.t("slots.new_title" if self.empty_only else "slots.title"))
        self.backend.text("front.options", self.backend.t("main.options"))
        self.backend.text("front.back", self.backend.t("common.back"))
        self.backend.text("front.hint", self.backend.t("slots.hint"))
        if self.modal:
            self.modal.refresh()

    @property
    def focused_slot(self):
        return min(3, self.grid.index // 2 + 1)

    def options(self):
        if self.modal is None:
            self.actions.execute(UICommand(C.OPEN_OPTIONS))

    def choose(self, slot):
        if self.modal is not None:
            return
        kind = C.SELECT_NEW_SLOT if self.empty_only else C.LOAD_SLOT
        message = self.actions.execute(UICommand(kind, str(slot)))
        if message:
            self.message.set(message)

    def load(self, actions, slot):
        self.choose(slot)

    def request_delete(self, slot=None):
        if self.modal is not None:
            return
        if slot is None and self.grid.index >= 6:
            return
        slot = slot or self.focused_slot
        if not self.rows[slot - 1].occupied:
            return
        try:
            self.info = self.query.slot_deletion(slot)
        except ValueError as error:
            self.message.set(self.backend.t(str(error)))
            return
        self.stage = 0
        self.show_dialog()

    def body(self):
        info, tr = self.info, self.backend.t
        text = tr("slots.delete_body", name=info.name, level=info.level,
            class_name=tr("class." + info.class_id + ".name"))
        if info.bloodstain_souls:
            text += "\n\n" + tr("slots.bloodstain_warning")
        if self.stage:
            text += "\n\n" + tr("slots.final_warning")
        if self.query.slot_in_use(info.slot):
            text += "\n\n" + tr("slots.in_use")
        return text

    def show_dialog(self):
        if self.modal:
            self.modal.root.destroy()
        self.modal = Dialog(self.backend, "slots.delete_title", self.body, self.accept_delete, self.cancel_delete,
            accept_label="slots.delete" if self.stage else "slots.review_delete", danger=bool(self.stage))
        self.modal.accept_button.enable(not self.query.slot_in_use(self.info.slot))

    def accept_delete(self):
        if self.query.slot_in_use(self.info.slot):
            return
        if not self.stage:
            self.stage = 1
            self.show_dialog()
            return
        message = self.actions.execute(UICommand(C.DELETE_SLOT, json.dumps(dict(slot=self.info.slot, updated_at=self.info.updated_at))))
        self.cancel_delete()
        self.refresh()
        self.grid.select(len(self.grid.buttons) - 1)
        self.message.set(message or self.backend.t("slots.deleted"))

    def cancel_delete(self):
        if self.modal:
            self.modal.root.destroy()
        self.modal, self.info = None, None

    def back(self):
        if self.modal:
            self.cancel_delete()
            return True
        return False

    def move(self, dx=0, dy=0):
        (self.modal or self.grid).move(dx, dy)

    def confirm(self):
        (self.modal or self.grid).confirm()

    def tick(self, dt=0):
        language = self.backend.t("locale.id")
        if language != self.language:
            self.language = language
            self.refresh()
        self.wait -= dt
        if self.modal and self.wait <= 0:
            self.wait = .25
            self.modal.accept_button.enable(not self.query.slot_in_use(self.info.slot))
            self.modal.refresh()
