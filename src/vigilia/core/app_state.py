"""Estados da aplicação e controladores testáveis sem janela."""

from collections.abc import Callable
from typing import Protocol
from dataclasses import dataclass

from vigilia.core.events import EventBus, AppStateChangedEvent
from vigilia.core.types import AppState as S

TRANSITIONS = {
    S.BOOT: {S.MAIN_MENU},
    S.MAIN_MENU: {S.CHARACTER_CREATION, S.SLOT_SELECT, S.OPTIONS, S.CREDITS, S.PLAYING, S.QUIT},
    S.CHARACTER_CREATION: {S.MAIN_MENU, S.SLOT_SELECT, S.PLAYING, S.QUIT},
    S.SLOT_SELECT: {S.MAIN_MENU, S.CHARACTER_CREATION, S.OPTIONS, S.PLAYING, S.QUIT},
    S.PLAYING: {S.PAUSED, S.MAIN_MENU, S.CREDITS, S.QUIT},
    S.PAUSED: {S.PLAYING, S.MAIN_MENU, S.OPTIONS, S.CREDITS, S.QUIT},
    S.OPTIONS: {S.MAIN_MENU, S.PAUSED, S.SLOT_SELECT, S.QUIT},
    S.CREDITS: {S.MAIN_MENU, S.PLAYING, S.QUIT},
    S.QUIT: set(),
}


class StateController(Protocol):
    def enter(self, previous: S) -> None: ...
    def exit(self, following: S) -> None: ...
    def tick(self, dt: float) -> None: ...


@dataclass
class CallbackController:
    on_enter: Callable[[S], None] = lambda previous: None
    on_exit: Callable[[S], None] = lambda following: None
    on_tick: Callable[[float], None] = lambda dt: None

    def enter(self, previous):
        self.on_enter(previous)

    def exit(self, following):
        self.on_exit(following)

    def tick(self, dt):
        self.on_tick(dt)


class AppStateMachine:
    def __init__(self, bus: EventBus):
        self.bus, self.current = bus, S.BOOT
        self.controllers: dict[S, StateController] = {}
        self._returns: list[S] = []

    @property
    def simulating(self):
        return self.current == S.PLAYING

    def register(self, state: S, controller: StateController):
        self.controllers[state] = controller

    def transition(self, following: S):
        if following == self.current:
            return
        if following not in TRANSITIONS[self.current]:
            raise ValueError(f"Transição inválida: {self.current} -> {following}")
        previous = self.current
        if previous in self.controllers:
            self.controllers[previous].exit(following)
        self.current = following
        if following in (S.MAIN_MENU, S.PLAYING, S.QUIT):
            self._returns.clear()
        if following in self.controllers:
            self.controllers[following].enter(previous)
        self.bus.publish(AppStateChangedEvent(previous, following))

    def push(self, following: S):
        previous = self.current
        self.transition(following)
        self._returns.append(previous)

    def back(self):
        following = self._returns[-1] if self._returns else S.MAIN_MENU
        self.transition(following)
        if self._returns:
            self._returns.pop()

    def tick(self, dt: float):
        if controller := self.controllers.get(self.current):
            controller.tick(dt)
