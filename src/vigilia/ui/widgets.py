"""Widgets testáveis com backend nativo ou simulado. Coordenadas locais em pixels."""

from collections.abc import Callable

from vigilia.core.protocols import IUIBackend
from vigilia.core.views import Rect
from vigilia.ui.text_render import make_text, INK, GOLD, PRIMARY

DARK = (.035, .047, .055, .94)
SURFACE = (.075, .09, .10, .97)
FOCUS = (.24, .19, .105, 1)


class Widget:
    def __init__(self, backend: IUIBackend, key: str) -> None:
        self.backend, self.key = backend, key

    def show(self) -> None:
        self.backend.visible(self.key, True)

    def hide(self) -> None:
        self.backend.visible(self.key, False)

    def destroy(self) -> None:
        self.backend.destroy(self.key)


class Panel(Widget):
    def __init__(self, backend, key, rect: Rect, *, parent=None, color=DARK):
        super().__init__(backend, key)
        backend.create(key, "panel", rect, parent=parent, color=color)


class Label(Widget):
    def __init__(self, backend, key, text: str, rect: Rect, *, parent=None, size=PRIMARY, color=INK):
        super().__init__(backend, key)
        self.value = text
        make_text(backend, key, text, rect, parent=parent, size=size, color=color)

    def set(self, value: str) -> None:
        if self.value != value:
            self.backend.text(self.key, value)
            self.value = value


class Button(Widget):
    def __init__(self, backend, key, text: str, rect: Rect, command: Callable[[], None], *, parent=None, size=PRIMARY, danger=False):
        super().__init__(backend, key)
        self._command = command
        self.enabled, self.focused = True, False
        self.surface, self.highlight = ((.34, .055, .04, 1), (.56, .10, .065, 1)) if danger else (SURFACE, FOCUS)
        backend.create(key, "button", rect, text=text, size=size, parent=parent, color=self.surface, command=self.activate)

    def activate(self) -> None:
        if self.enabled:
            if hasattr(self.backend, "feedback"):
                self.backend.feedback("ui_click")
            self._command()

    def enable(self, enabled: bool) -> None:
        self.enabled = enabled
        self.backend.enabled(self.key, enabled)

    def focus(self, value: bool) -> None:
        if self.focused != value:
            self.focused = value
            self.backend.color(self.key, self.highlight if value else self.surface)
            if hasattr(self.backend, "focus_outline"):
                self.backend.focus_outline(self.key, value)
            if value and hasattr(self.backend, "feedback"):
                self.backend.feedback("ui_hover")


class Bar(Panel):
    def __init__(self, backend, key, rect: Rect, color, *, parent=None):
        super().__init__(backend, key, rect, parent=parent, color=(.10, .10, .105, 1))
        self.fill = Panel(backend, key + ".fill", (0, 0, rect[2], rect[3]), parent=key, color=color)
        self.ratio = None

    def set(self, value: float, maximum: float) -> None:
        ratio = max(0, min(1, value / maximum)) if maximum > 0 else 0
        if ratio != self.ratio:
            self.backend.fraction(self.fill.key, ratio)
            self.ratio = ratio


class Grid:
    def __init__(self, buttons: list[Button], columns: int = 1):
        self.buttons, self.columns, self.index = buttons, columns, 0
        if buttons:
            buttons[0].focus(True)

    def select(self, index: int) -> None:
        if not self.buttons:
            return
        self.buttons[self.index].focus(False)
        self.index = index % len(self.buttons)
        self.buttons[self.index].focus(True)

    def move(self, dx=0, dy=0) -> None:
        if not self.buttons:
            return
        step = dx + dy * self.columns
        target = self.index
        for _ in self.buttons:
            target = (target + step) % len(self.buttons)
            if self.buttons[target].enabled:
                self.select(target)
                return

    def confirm(self) -> None:
        if self.buttons:
            self.buttons[self.index].activate()


class Slider(Widget):
    def __init__(self, backend, key, rect, value, command, *, parent=None, minimum=0., maximum=1.):
        super().__init__(backend, key)
        backend.create(key, "slider", rect, parent=parent, value=value, minimum=minimum, maximum=maximum, command=command)

class Tooltip(Label):
    """Descrição do item sob foco, compartilhada por mouse e controle."""


class TextInput(Widget):
    def __init__(self, backend, key, value, rect, *, parent=None, size=PRIMARY):
        super().__init__(backend, key)
        backend.create(key, "entry", rect, text=value, size=size, parent=parent)

    @property
    def value(self):
        return self.backend.read_text(self.key)

    def focus(self):
        self.backend.focus_text(self.key, True)
