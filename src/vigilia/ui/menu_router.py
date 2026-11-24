"""Um roteador recebe todo input de menu enquanto a simulação está congelada."""

from vigilia.core.protocols import IMenuInput, IUIActions, IStatsQuery, IInventoryQuery
from vigilia.core.types import Action
from vigilia.core.views import UICommand, UICommandKind
from vigilia.ui.pause_menu import PauseMenu, PAGES
from vigilia.ui.status_ui import StatusUI
from vigilia.ui.inventory_ui import InventoryUI
from vigilia.ui.level_up_ui import LevelUpUI
from vigilia.ui.map_view import MapView
from vigilia.ui.ending_ui import EndingUI

DIRECTIONS = {Action.MENU_UP: (0, -1), Action.MENU_DOWN: (0, 1),
              Action.MENU_LEFT: (-1, 0), Action.MENU_RIGHT: (1, 0)}


class MenuRouter:
    def navigate(self, edge, *, scene=None, on_back=None):
        if not edge.pressed:
            return
        if scene is None:
            self.handle(edge.action)
            return
        action = edge.action
        if action == Action.MENU_BACK:
            if self.backend.text_active():
                scene.cancel_text()
            elif not (hasattr(scene, "back") and scene.back()):
                on_back()
        elif action in DIRECTIONS:
            scene.move(*DIRECTIONS[action])
        elif action == Action.MENU_CONFIRM:
            scene.confirm()
        elif action == Action.MENU_DELETE and hasattr(scene, "request_delete"):
            scene.request_delete()
        elif action in (Action.MENU_TAB_NEXT, Action.MENU_TAB_PREVIOUS) and hasattr(scene, "change_category"):
            scene.change_category(1 if action == Action.MENU_TAB_NEXT else -1)
    def __init__(self, backend, input_source: IMenuInput, stats: IStatsQuery, inventory: IInventoryQuery, actions: IUIActions, *, map_query=None):
        self.backend, self.input, self.stats, self.inventory, self.actions = backend, input_source, stats, inventory, actions
        self.page = None
        self.shell = self.content = None
        self._repeat_action, self._repeat_time = None, 0
        self.map_query = map_query

    @property
    def opened(self):
        return self.page is not None

    def open(self, page="pause"):
        if page in ("options", "main"):
            self.actions.execute(UICommand(UICommandKind.OPEN_OPTIONS if page == "options" else UICommandKind.MAIN_MENU))
            return
        if page == "resume":
            self.close()
            self.actions.execute(UICommand(UICommandKind.RESUME))
            return
        if self.shell is not None:
            self.shell.root.destroy()
        self.page, self.content = page, None
        self._repeat_action, self._repeat_time = None, 0
        self.shell = PauseMenu(self.backend, self.open)
        if page in dict(PAGES):
            self.shell.grid.select(next(index for index, (key, _) in enumerate(PAGES) if key == page))
        if page in ("pause", "status"):
            self.content = StatusUI(self.backend, self.stats)
        elif page in ("inventory", "equipment"):
            self.content = InventoryUI(self.backend, self.inventory, self.actions, equipment=page == "equipment")
        elif page == "level":
            self.content = LevelUpUI(self.backend, self.stats, self.actions)
        elif page == "ending":
            self.content = EndingUI(self.backend, self.actions)
        elif page == "map" and self.map_query is not None:
            self.content = MapView(self.backend, self.map_query)

    def close(self):
        if self.shell is not None:
            self.shell.root.destroy()
        self.shell = self.content = self.page = None
        self._repeat_action = None

    def _direction(self, action):
        dx, dy = DIRECTIONS[action]
        if self.content is not None and hasattr(self.content, "move"):
            self.content.move(dx, dy)
        elif self.page == "pause":
            self.shell.grid.move(dx, dy)

    def handle(self, action):
        if action == Action.MENU_BACK:
            if self.content is not None and hasattr(self.content, "back") and self.content.back():
                return
            self.open("resume" if self.page == "pause" else "pause")
        elif action in DIRECTIONS:
            self._direction(action)
        elif action == Action.MENU_CONFIRM:
            if self.content is not None and hasattr(self.content, "confirm"):
                self.content.confirm()
            elif self.page == "pause":
                self.shell.grid.confirm()
        elif action in (Action.MENU_TAB_NEXT, Action.MENU_TAB_PREVIOUS) and isinstance(self.content, InventoryUI):
            self.content.change_category(1 if action == Action.MENU_TAB_NEXT else -1)
        elif action.value.startswith("level_") and isinstance(self.content, LevelUpUI):
            stat = action.value.removeprefix("level_")
            index = next(index for index, value in enumerate(self.content.view.attributes) if value.id == stat)
            # O comando também valida custo e fogueira, inclusive no atalho numérico.
            self.content.apply_index(index)

    def tick(self, dt):
        if self.content is not None and hasattr(self.content, "tick"):
            self.content.tick()
        while self.opened and (edge := self.input.menu_next_edge()) is not None:
            if edge.pressed:
                self.navigate(edge)
                if self.opened and edge.action in DIRECTIONS:
                    self._repeat_action, self._repeat_time = edge.action, .35
        if not self.opened:
            return
        held = self.input.menu_held().actions
        if self._repeat_action not in held:
            self._repeat_action = None
        elif self._repeat_action is not None:
            self._repeat_time -= dt
            if self._repeat_time <= 0:
                self._direction(self._repeat_action)
                self._repeat_time = .11
