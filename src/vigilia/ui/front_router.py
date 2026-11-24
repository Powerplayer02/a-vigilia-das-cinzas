"""Controladores de telas de borda, sem conhecimento de engine ou domínio."""

from vigilia.core.types import AppState as S, Action
from vigilia.core.views import UICommand, UICommandKind as C
from vigilia.ui.main_menu import MainMenu, Credits
from vigilia.ui.character_creation import CharacterCreation
from vigilia.ui.slot_select import SlotSelect
from vigilia.ui.options_ui import OptionsUI
from vigilia.ui.menu_router import DIRECTIONS, MenuRouter


class FrontRouter:
    def __init__(self, backend, query, actions, input_source, *, navigator=None):
        self.backend, self.query, self.actions, self.input = backend, query, actions, input_source
        self.screen, self.repeat, self.wait = None, None, 0
        self.navigator = navigator
        self.factories = {S.MAIN_MENU: MainMenu,
                          S.CHARACTER_CREATION: lambda b, q, a: CharacterCreation(b, q, a, slot=q.creation_slot()),
                          S.SLOT_SELECT: lambda b, q, a: SlotSelect(b, q, a, empty_only=q.slot_selection_mode() == "create"), S.CREDITS: Credits,
                          S.OPTIONS: lambda b, q, a: OptionsUI(b, q, a, input_source)}

    @property
    def opened(self):
        return self.screen is not None

    def show(self, state):
        self.close()
        self.screen = self.factories[state](self.backend, self.query, self.actions)

    def close(self):
        if self.screen is not None:
            self.screen.root.destroy()
        self.screen, self.repeat, self.wait = None, None, 0

    def handle(self, action):
        if self.navigator is not None:
            from vigilia.core.types import InputEdge
            self.navigator.navigate(InputEdge(action, True), scene=self.screen, on_back=lambda: self.actions.execute(UICommand(C.BACK)))
            return
        screen = self.screen
        if action == Action.MENU_BACK:
            if self.backend.text_active():
                screen.cancel_text()
            elif not (hasattr(screen, "back") and screen.back()):
                self.actions.execute(UICommand(C.BACK))
        elif action in DIRECTIONS:
            screen.move(*DIRECTIONS[action])
        elif action == Action.MENU_CONFIRM:
            screen.confirm()
        elif action == Action.MENU_DELETE and hasattr(screen, "request_delete"):
            screen.request_delete()
        elif action in (Action.MENU_TAB_NEXT, Action.MENU_TAB_PREVIOUS) and hasattr(screen, "change_category"):
            screen.change_category(1 if action == Action.MENU_TAB_NEXT else -1)

    def tick(self, dt):
        if self.screen is not None and hasattr(self.screen, "tick"):
            self.screen.tick(dt)
        while self.screen is not None and (edge := self.input.menu_next_edge()) is not None:
            if edge.pressed:
                self.handle(edge.action)
                if self.screen is not None and edge.action in DIRECTIONS:
                    self.repeat, self.wait = edge.action, .35
        if self.screen is None:
            return
        if self.repeat not in self.input.menu_held().actions:
            self.repeat = None
        elif self.repeat is not None:
            self.wait -= dt
            if self.wait <= 0:
                self.handle(self.repeat)
                self.wait = .11
