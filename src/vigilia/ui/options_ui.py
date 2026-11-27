"""PreferÃªncias por aÃ§Ãµes: sliders, conflitos e resets acessÃ­veis por foco."""

import json
from vigilia.core.views import UICommand, UICommandKind as C
from vigilia.ui.main_menu import sheet
from vigilia.ui.widgets import Label, Button, Grid, Slider
from vigilia.ui.dialog import Dialog
from vigilia.ui.text_render import GOLD, SECONDARY

CATEGORIES = ("graphics", "audio", "controls", "language", "accessibility")


class OptionsUI:
    def __init__(self, backend, query, actions, input_source):
        self.backend, self.query, self.actions, self.input = backend, query, actions, input_source
        self.category, self.page, self.capture = 0, 0, None
        self.device, self.modal, self.root = "keyboard", None, None
        self.pending = None
        self.render()

    def rows_query(self):
        category = CATEGORIES[self.category]
        return self.query.option_rows("gamepad" if category == "controls" and self.device == "gamepad" else category)

    def render(self, message="", focus=0):
        if self.root is not None:
            self.root.destroy()
        self.modal = None
        b = self.backend
        self.root = sheet(b, "options.title")
        for i, category in enumerate(CATEGORIES):
            button = Button(b, "front.tab." + category, b.t("options." + category), (164 + i * 188, 126, 176, 42),
                            lambda index=i: self.select_category(index), parent="front", size=SECONDARY,
                            icon={"graphics":"spell","audio":"volume","controls":"controls","language":"credits","accessibility":"heart"}[category])
            button.focus(i == self.category)
        all_rows = self.rows_query()
        self.page_count = max(1, (len(all_rows) + 7) // 8)
        self.page %= self.page_count
        self.rows = all_rows[self.page * 8:(self.page + 1) * 8]
        self.buttons = []
        for i, row in enumerate(self.rows):
            button = Button(b, "front.option." + row.id, f"{row.label}     {row.value}",
                (164, 190 + i * 43, 600 if row.numeric is not None else 928, 38),
                lambda index=i: self.change(index, 1), parent="front", size=SECONDARY)
            self.buttons.append(button)
            if row.numeric is not None:
                Slider(b, "front.slider." + row.id, (794, 198 + i * 43, 294, 22), row.numeric,
                    lambda value, index=i: self.set_slider(index, value), parent="front", minimum=row.minimum, maximum=row.maximum)
        if self.page_count > 1:
            self.buttons.append(Button(b, "front.page.prev", "<", (164, 548, 50, 32), lambda: self.turn_page(-1), parent="front"))
            self.buttons.append(Button(b, "front.page.next", ">", (224, 548, 50, 32), lambda: self.turn_page(1), parent="front"))
            Label(b, "front.page", b.t("options.page", current=self.page + 1, total=self.page_count), (292, 550, 400, 28), parent="front", size=SECONDARY)
        if CATEGORIES[self.category] == "controls":
            self.buttons.append(Button(b, "front.device", b.t("options.device." + self.device), (786, 548, 306, 32), self.toggle_device, parent="front", size=SECONDARY))
        self.buttons.append(Button(b, "front.reset.tab", b.t("options.reset_tab"), (164, 600, 432, 36), self.reset_tab, parent="front", size=SECONDARY))
        self.buttons.append(Button(b, "front.reset.all", b.t("options.reset_all"), (616, 600, 476, 36), self.reset_all, parent="front", size=SECONDARY))
        self.grid = Grid(self.buttons)
        self.grid.select(focus)
        hint = "options.controls_hint" if CATEGORIES[self.category] == "controls" else "common.adjust_hint"
        self.message = Label(b, "front.message", message or b.t(hint), (164, 566, 928, 28), parent="front", size=SECONDARY, color=GOLD)

    def select_category(self, index):
        if self.modal or self.capture:
            return
        self.category, self.page = index % len(CATEGORIES), 0
        self.render()

    def change_category(self, delta):
        self.select_category(self.category + delta)

    def toggle_device(self):
        if self.modal or self.capture:
            return
        self.device, self.page = ("gamepad" if self.device == "keyboard" else "keyboard"), 0
        self.render()

    def turn_page(self, delta):
        if not self.modal and not self.capture:
            self.page += delta
            self.render()

    def move(self, dx=0, dy=0):
        if self.modal:
            self.modal.move(dx, dy)
            return
        index = self.grid.index
        if CATEGORIES[self.category] == "controls" and index < len(self.rows):
            if dx and self.rows[index].id in ("mouse_sensitivity", "ultrakill_style"):
                self.change(index, dx)
            elif dx:
                self.turn_page(dx)
            elif index + dy >= len(self.rows) and self.page + 1 < self.page_count:
                self.page += 1
                self.render()
            elif index + dy < 0 and self.page > 0:
                self.page -= 1
                self.render(focus=7)
            else:
                self.grid.move(dy=dy)
        elif dx and index < len(self.rows):
            self.change(index, dx)
        else:
            self.grid.move(dx, dy)

    def confirm(self):
        (self.modal or self.grid).confirm()

    def change(self, index, delta):
        if self.modal:
            return
        row = self.rows[index]
        if CATEGORIES[self.category] == "controls" and row.id not in ("mouse_sensitivity", "ultrakill_style"):
            self.capture = row.id
            self.input.begin_binding_capture(self.device)
            self.message.set(self.backend.t("options.capture"))
            return
        message = self.actions.execute(UICommand(C.SET_OPTION, json.dumps(dict(key=row.id, delta=delta))))
        self.render(message, focus=index)

    def set_slider(self, index, value):
        if self.modal or index >= len(self.rows):
            return
        row = self.rows[index]
        message = self.actions.execute(UICommand(C.SET_OPTION, json.dumps(dict(key=row.id, value=float(value)))))
        self.rows = self.rows_query()[self.page * 8:(self.page + 1) * 8]
        updated = self.rows[index]
        self.backend.text(self.buttons[index].key, f"{updated.label}     {updated.value}")
        self.message.set(message)

    def reset_tab(self):
        if not self.modal:
            message = self.actions.execute(UICommand(C.RESET_OPTIONS, CATEGORIES[self.category]))
            self.render(message)

    def reset_all(self):
        if self.modal:
            return
        self.modal = Dialog(self.backend, "options.reset_title", lambda: self.backend.t("options.reset_warning"),
            self.accept_reset_all, self.close_dialog, accept_label="options.reset_all", danger=True)

    def accept_reset_all(self):
        self.close_dialog()
        message = self.actions.execute(UICommand(C.RESET_OPTIONS, "all"))
        self.render(message)

    def close_dialog(self):
        if self.modal:
            self.modal.root.destroy()
        self.modal = None

    def back(self):
        if self.modal:
            self.close_dialog()
            return True
        return False

    def accept_conflict(self):
        payload = self.pending | {"replace_conflicts": True}
        self.close_dialog()
        message = self.actions.execute(UICommand(C.REBIND, json.dumps(payload)))
        self.pending = None
        self.render(message)

    def tick(self, dt=0):
        if not self.capture:
            return
        key = self.input.captured_binding()
        if key is None:
            if hasattr(self.input, "arm_mouse_capture"):
                self.input.arm_mouse_capture()
            return
        action, self.capture = self.capture, None
        if key == "escape":
            self.render()
            return
        self.pending = dict(action=action, binding=key, device=self.device)
        conflicts = self.query.binding_conflicts(action, key, self.device) if hasattr(self.query, "binding_conflicts") else ()
        if conflicts:
            self.modal = Dialog(self.backend, "options.conflict_title",
                lambda: self.backend.t("options.conflict_body", binding=key.upper(), other_action=", ".join(conflicts)),
                self.accept_conflict, self.close_dialog, accept_label="options.replace_binding", danger=True)
        else:
            message = self.actions.execute(UICommand(C.REBIND, json.dumps(self.pending)))
            self.pending = None
            self.render(message)
