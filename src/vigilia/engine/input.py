"""Mapeamento de controles e fila de bordas independente da taxa de render."""

from collections import deque
from collections.abc import Mapping
from math import hypot
from enum import StrEnum

from vigilia.core.config import DEFAULT_KEYMAP, DEFAULT_PADMAP
from vigilia.core.types import Action, HeldState, InputEdge

_ALIASES = {
    "lshift": "shift", "rshift": "shift", "lcontrol": "control",
    "rcontrol": "control", "lalt": "alt", "ralt": "alt",
}


class InputMode(StrEnum):
    GAMEPLAY = "gameplay"
    MENU = "menu"


MENU_KEYS = {
    Action.MENU_UP: ("arrow_up", "w"), Action.MENU_DOWN: ("arrow_down", "s"),
    Action.MENU_LEFT: ("arrow_left", "a"), Action.MENU_RIGHT: ("arrow_right", "d"),
    Action.MENU_CONFIRM: ("enter", "space", "e"), Action.MENU_BACK: ("escape",),
    Action.MENU_TAB_NEXT: ("tab",), Action.MENU_TAB_PREVIOUS: ("shift-tab",),
    Action.MENU_DELETE: ("delete",),
}
MENU_PAD = {
    Action.MENU_UP: "dpad_up", Action.MENU_DOWN: "dpad_down",
    Action.MENU_LEFT: "dpad_left", Action.MENU_RIGHT: "dpad_right",
    Action.MENU_CONFIRM: "face_a", Action.MENU_BACK: "face_b",
    Action.MENU_TAB_NEXT: "rshoulder", Action.MENU_TAB_PREVIOUS: "lshoulder",
    Action.MENU_DELETE: "face_x",
}


class InputManager:
    """Mantém ações contínuas e entrega cada borda uma vez em ordem FIFO."""

    def __init__(self, bindings: Mapping[Action, str] = DEFAULT_KEYMAP,
                 gamepad: Mapping[Action, str] = DEFAULT_PADMAP) -> None:
        self._bindings = dict(bindings)
        self._gamepad = dict(gamepad)
        self._keys: set[str] = set()
        self._buttons: frozenset[str] = frozenset()
        self._actions: frozenset[Action] = frozenset()
        self._edges: deque[InputEdge] = deque()
        self._stick = (0.0, 0.0)
        self.mode = InputMode.GAMEPLAY
        self._agile_enabled = False
        self._menu_edges: deque[InputEdge] = deque()
        self._suppressed_keys: set[str] = set()
        self._suppressed_buttons: set[str] = set()
        self._suppress_stick = False
        self._text_capture = False
        self._binding_capture = False
        self._captured_binding = None
        self._capture_held: set[str] = set()

    def set_text_capture(self, active: bool) -> None:
        self._text_capture = active
        self._menu_edges.clear()
        self._actions = frozenset()
        self._suppressed_keys.update(self._keys)

    def begin_binding_capture(self, device="keyboard") -> None:
        self._binding_capture, self._captured_binding = True, None
        self._capture_device = device
        self._capture_mouse_armed = False
        self._capture_buttons = set(self._buttons)
        self._capture_held = self._keys.copy()
        self._suppressed_keys.update(self._keys)
        self._menu_edges.clear()
        self._actions = frozenset()

    def captured_binding(self) -> str | None:
        value, self._captured_binding = self._captured_binding, None
        return value

    def arm_mouse_capture(self):
        self._capture_mouse_armed = True

    def set_mode(self, mode: InputMode, *, force=False) -> None:
        if mode == self.mode and not force:
            return
        self.mode = mode
        self._edges.clear()
        self._menu_edges.clear()
        self._actions = frozenset()
        self._suppressed_keys = self._keys.copy()
        self._suppressed_buttons = set(self._buttons)
        self._suppress_stick = hypot(*self._stick) > 0

    def set_agile_enabled(self, enabled: bool) -> None:
        if enabled != self._agile_enabled:
            self._agile_enabled = enabled
            self.set_mode(self.mode, force=True)

    def menu_request(self) -> InputEdge | None:
        """Captura a abertura de menu no render, antes de avançar qualquer passo."""
        if self.mode != InputMode.GAMEPLAY:
            return None
        for edge in self._edges:
            if edge.pressed and edge.action in (Action.PAUSE, Action.OPEN_INVENTORY, Action.OPEN_STATUS, Action.OPEN_LEVEL_UP):
                self._edges.remove(edge)
                return edge
        return None

    def rebind(self, action: Action, binding: str, *, device="keyboard") -> None:
        """Atualiza o vínculo de teclado e recalcula as ações ativas."""
        chord = binding.lower().strip().replace("ctrl", "control")
        if chord and not all(chord.split("-")):
            raise ValueError("Informe um botão ou uma combinação como shift-r.")
        (self._gamepad if device == "gamepad" else self._bindings)[Action(action)] = chord
        self._refresh()

    def key(self, key: str, pressed: bool) -> None:
        """Registra eventos individuais, incluindo toques entre dois renders."""
        if pressed:
            self._keys.add(key)
        else:
            self._keys.discard(key)
            self._suppressed_keys.discard(key)
            self._capture_held.discard(key)
        if pressed and self._binding_capture and key not in self._capture_held and (not key.startswith("mouse") or self._capture_mouse_armed) and key not in ("shift", "control", "alt", "lshift", "rshift", "lcontrol", "rcontrol") and (getattr(self, "_capture_device", "keyboard") == "keyboard" or key == "escape"):
            modifiers = [name for name in ("shift", "control", "alt") if name in self._keys or "l" + name in self._keys or "r" + name in self._keys]
            self._captured_binding = "escape" if key == "escape" else "-".join((*modifiers, key))
            self._binding_capture = False
            self._suppressed_keys.update(self._keys)
        self._refresh()

    def poll_gamepad(self, buttons: frozenset[str], x: float, y: float) -> None:
        """Atualiza botões e aplica zona morta radial ao analógico esquerdo."""
        if self._binding_capture and getattr(self, "_capture_device", "keyboard") == "gamepad":
            self._capture_buttons.intersection_update(buttons)
            fresh = buttons - self._capture_buttons
            if fresh:
                self._captured_binding = sorted(fresh)[0]
                self._binding_capture = False
                self._suppressed_buttons.update(buttons)
        self._buttons = buttons
        self._suppressed_buttons.intersection_update(buttons)
        length = hypot(x, y)
        scale = (min(1.0, length) - 0.18) / (0.82 * length) if length > 0.18 else 0.0
        self._stick = (x * scale, y * scale)
        if length <= .18:
            self._suppress_stick = False
        self._refresh()

    def _refresh(self) -> None:
        available = self._keys - self._suppressed_keys
        keys = available | {_ALIASES.get(key, key) for key in available}
        buttons = self._buttons - self._suppressed_buttons
        if self.mode == InputMode.GAMEPLAY:
            actions = frozenset(
                action for action, chord in self._bindings.items()
                if keys.issuperset(chord.replace("ctrl", "control").split("-"))
            ) | frozenset(action for action, button in self._gamepad.items() if button in buttons)
            if not self._agile_enabled:
                actions -= {Action.DASH, Action.SLIDE, Action.JUMP}
        else:
            actions = frozenset(action for action, bindings in MENU_KEYS.items()
                if any(keys.issuperset(chord.split("-")) for chord in bindings))
            if "shift" in keys:
                actions -= {Action.MENU_TAB_NEXT}
            actions |= frozenset(action for action, button in MENU_PAD.items() if button in buttons)
            if "start" in buttons:
                actions |= {Action.MENU_BACK}
            actions |= frozenset(action for action, chord in self._bindings.items()
                if action.value.startswith("level_") and keys.issuperset(chord.split("-")))
            if not self._suppress_stick:
                x, y = self._stick
                if abs(x) > .55 or abs(y) > .55:
                    actions |= {Action.MENU_RIGHT if x > 0 else Action.MENU_LEFT} if abs(x) > abs(y) else {
                        Action.MENU_UP if y > 0 else Action.MENU_DOWN}
            if self._text_capture:
                actions &= {Action.MENU_BACK}
            if self._binding_capture:
                actions = frozenset()
        queue = self._edges if self.mode == InputMode.GAMEPLAY else self._menu_edges
        for action in sorted(self._actions ^ actions):
            queue.append(InputEdge(action, action in actions))
        self._actions = actions

    def next_edge(self) -> InputEdge | None:
        """Retira a borda mais antiga, quando houver."""
        return self._edges.popleft() if self.mode == InputMode.GAMEPLAY and self._edges else None

    def held(self) -> HeldState:
        """Combina teclado e analógico, limitando o comprimento a um."""
        if self.mode != InputMode.GAMEPLAY:
            return HeldState()
        x, y = (0, 0) if self._suppress_stick else self._stick
        x += (Action.MOVE_RIGHT in self._actions) - (Action.MOVE_LEFT in self._actions)
        y += (Action.MOVE_FORWARD in self._actions) - (Action.MOVE_BACK in self._actions)
        length = max(1.0, hypot(x, y))
        return HeldState(self._actions, x / length, y / length)

    def menu_next_edge(self) -> InputEdge | None:
        return self._menu_edges.popleft() if self.mode == InputMode.MENU and self._menu_edges else None

    def menu_held(self) -> HeldState:
        return HeldState(self._actions) if self.mode == InputMode.MENU else HeldState()

    def reset(self) -> None:
        """Libera botões e limpa eventos pendentes ao perder o foco."""
        self._keys.clear()
        self._buttons = frozenset()
        self._actions = frozenset()
        self._edges.clear()
        self._menu_edges.clear()
        self._suppressed_keys.clear()
        self._suppressed_buttons.clear()
        self._suppress_stick = False
        self._binding_capture, self._captured_binding = False, None
        self._stick = (0.0, 0.0)
