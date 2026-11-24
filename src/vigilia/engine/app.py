"""Janela Panda3D, coleta de controles e estados da aplicação."""

from collections.abc import Callable
from typing import Protocol

from direct.showbase.ShowBase import ShowBase
from direct.task.Task import Task
from panda3d.core import (
    ClockObject, GraphicsWindow, InputDevice, ModifierButtons, WindowProperties,
    load_prc_file_data,
)

from vigilia.core.config import Config
from vigilia.core.log import configure_logging, shutdown_logging
from vigilia.core.types import GameState


class ArenaLoop(Protocol):
    def start(self) -> None: ...
    def frame(self, elapsed: float, mouse: tuple[float, float],
              stick: tuple[float, float]) -> None: ...
    def keyboard(self, name: str, pressed: bool) -> None: ...
    def gamepad(self, buttons: frozenset[str], x: float, y: float) -> None: ...
    def reset_input(self) -> None: ...


class ArenaApp(ShowBase):
    """Traduz eventos nativos em entradas para o loop da arena."""

    def __init__(self, config: Config, *, window_type: str = "onscreen") -> None:
        configure_logging()
        load_prc_file_data("vigilia", f"""
            window-title A Vigília das Cinzas
            win-size {config.width} {config.height}
            load-display pandagl
            audio-library-name null
            sync-video {str(config.vsync).lower()}
            fullscreen {str(config.fullscreen).lower()}
            framebuffer-multisample true
            multisamples 4
            textures-power-2 none
        """)
        super().__init__(windowType=window_type)
        self.disable_mouse()
        self.state = GameState.LOADING
        self._game: ArenaLoop | None = None
        self._clock = ClockObject.get_global_clock()
        self._pointer: tuple[int, int] | None = None
        self._focused = isinstance(self.win, GraphicsWindow)
        if isinstance(self.win, GraphicsWindow) and self.buttonThrowers:
            thrower = self.buttonThrowers[0].node()
            thrower.set_modifier_buttons(ModifierButtons())
            thrower.set_button_down_event("vigilia-button-down")
            thrower.set_button_up_event("vigilia-button-up")
            self.accept("vigilia-button-down", self._keyboard, [True])
            self.accept("vigilia-button-up", self._keyboard, [False])

    def start(self, game: ArenaLoop) -> None:
        """Instala a arena e a task de atualização antes do render do Panda."""
        self._game = game
        game.start()
        if self.state == GameState.LOADING:
            self.set_paused(False)
        self.taskMgr.add(self._update, "vigilia-update", sort=10)

    def apply_config(self, config: Config) -> None:
        if isinstance(self.win, GraphicsWindow):
            props = WindowProperties()
            props.set_size(config.width, config.height)
            self.win.request_properties(props)

    def finish(self) -> None:
        self.taskMgr.stop()

    def destroy(self):
        if getattr(self, "diagnostics", None) is not None:
            self.diagnostics.close()
        game = getattr(self, "_game", None)
        if game is not None and hasattr(game, "close"):
            game.close()
        super().destroy()
        shutdown_logging()

    def userExit(self) -> None:
        if self._game is not None and hasattr(self._game, "request_quit"):
            self._game.request_quit()
        else:
            self.finish()

    def set_paused(self, paused: bool) -> None:
        """Alterna o estado e ajusta o cursor para o modo atual."""
        self.state = GameState.PAUSED if paused else GameState.PLAYING
        self._pointer = None
        if isinstance(self.win, GraphicsWindow):
            props = WindowProperties()
            props.set_cursor_hidden(not paused)
            self.win.request_properties(props)

    def _keyboard(self, pressed: bool, name: str) -> None:
        if self._game is not None and self._focused:
            if pressed and name == "f10" and self.state == GameState.PAUSED:
                self.userExit()
            self._game.keyboard(name, pressed)

    def _mouse_delta(self) -> tuple[float, float]:
        window = self.win
        if (not isinstance(window, GraphicsWindow) or not self._focused
                or self.state != GameState.PLAYING or not window.has_pointer(0)):
            self._pointer = None
            return 0, 0
        pointer = window.get_pointer(0)
        if not pointer.get_in_window():
            self._pointer = None
            return 0, 0
        current = (pointer.get_x(), pointer.get_y())
        center = (window.get_x_size() // 2, window.get_y_size() // 2)
        previous = self._pointer or current
        self._pointer = center if window.move_pointer(0, *center) else current
        return current[0] - previous[0], current[1] - previous[1]

    def _poll_pad(self, receive: Callable[[frozenset[str], float, float], None]
                  ) -> tuple[float, float]:
        devices = self.devices.get_devices(InputDevice.DeviceClass.gamepad)
        if not self._focused or not devices:
            receive(frozenset(), 0, 0)
            return 0, 0
        pad = devices[0]
        pad.poll()
        buttons = {button.handle.get_name() for button in pad.buttons if button.pressed}
        axes = {axis.axis: axis.value for axis in pad.axes if axis.known}
        kind = InputDevice.Axis
        buttons.update(axis.name for axis in (kind.left_trigger, kind.right_trigger)
                       if axes.get(axis, 0) > .5)
        receive(frozenset(buttons), axes.get(kind.left_x, 0), axes.get(kind.left_y, 0))
        right_x, right_y = axes.get(kind.right_x, 0), axes.get(kind.right_y, 0)
        return (right_x if abs(right_x) > 0.18 else 0.0,
                right_y if abs(right_y) > 0.18 else 0.0)

    def _update(self, task: Task) -> int:
        assert self._game is not None
        if isinstance(self.win, GraphicsWindow):
            focused = self.win.get_properties().get_foreground()
            if self._focused and not focused:
                self._game.reset_input()
                self.set_paused(True)
            self._focused = focused
        stick = self._poll_pad(self._game.gamepad)
        self._game.frame(self._clock.get_dt(), self._mouse_delta(), stick)
        return task.cont
