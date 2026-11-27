"""Mapa estático em coordenadas do mundo, com descoberta incremental."""

from vigilia.core.protocols import IMapDataProvider
from vigilia.core.mathx import Vec3
from vigilia.ui.widgets import Panel, Label, Sprite
from vigilia.ui.text_render import TITLE, GOLD, MUTED, SECONDARY


class MapView:
    def __init__(self, backend, query: IMapDataProvider):
        self.backend, self.query, self.content, self.previous = backend, query, None, None
        self.root = Panel(backend, "menu.map", (410, 138, 672, 466), parent="menu", color=(0, 0, 0, 0))
        self.selection, self.focused = 0, False
        point = query.player_position()
        for index, region in enumerate(query.regions()):
            x, y, width, height = region.bounds
            if x <= point.x <= x+width and y <= point.y <= y+height:
                self.selection = index
        self.tick()

    def project(self, position):
        x, y, scale, offset_x, offset_y = self.projection
        return offset_x + (position.x - x) * scale, offset_y - (position.y - y) * scale

    def tick(self):
        state = self.query.discovered_areas(), self.query.discovered_bonfires(), self.query.player_position(), self.selection, self.focused
        if state == self.previous:
            return
        self.previous = state
        if self.content is not None:
            self.content.destroy()
        b = self.backend
        self.content = Panel(b, "menu.map.content", (0, 0, 672, 466), parent=self.root.key, color=(0, 0, 0, 0))
        Label(b, "menu.map.title", b.t("map.title"), (14, 0, 630, 42), parent=self.content.key, size=TITLE, color=GOLD)
        if not state[0]:
            Label(b, "menu.map.empty", b.t("map.empty"), (14, 80, 600, 80), parent=self.content.key, color=MUTED)
            return
        all_regions = self.query.regions()
        self.selection %= len(all_regions)
        selected = all_regions[self.selection]
        regions = (selected,) if self.focused else all_regions
        Label(b, "menu.map.selection", b.t("map.navigate", name=b.t("area." + selected.id)), (14, 44, 630, 28), parent=self.content.key, size=SECONDARY, color=GOLD)
        min_x = min(region.bounds[0] for region in regions)
        min_y = min(region.bounds[1] for region in regions)
        max_x = max(region.bounds[0] + region.bounds[2] for region in regions)
        max_y = max(region.bounds[1] + region.bounds[3] for region in regions)
        scale = min(610 / max(1, max_x - min_x), 280 / max(1, max_y - min_y))
        self.projection = (min_x, min_y, scale, 24 + (610 - (max_x-min_x)*scale)/2, 340)
        for region in regions:
            x, y, width, height = region.bounds
            px, py = self.project(Vec3(x, y + height))
            Panel(b, "menu.map.region." + region.id, (px, py, width * scale, height * scale),
                  parent=self.content.key, color=(.13, .17, .18, 1) if region.id == "patio_da_vigilia" else (.20, .15, .09, 1))
            Label(b, "menu.map.name." + region.id, (b.t("area." + region.id) if self.focused else str(all_regions.index(region)+1)), (px + 6, py + 8, width * scale - 12, 46),
                  parent=self.content.key, size=14, color=GOLD)
        for marker in self.query.bonfires():
            if not (min_x <= marker.position.x <= max_x and min_y <= marker.position.y <= max_y):
                continue
            x, y = self.project(marker.position)
            Sprite(b, "menu.map.bonfire." + marker.id, "bonfire", (x - 10, y - 12, 24, 24), parent=self.content.key)
        x, y = self.project(state[2])
        Sprite(b, "menu.map.player", "player", (x + 12, y - 8, 24, 24), parent=self.content.key)
        if not (min_x <= state[2].x <= max_x and min_y <= state[2].y <= max_y):
            b.visible("menu.map.player", False)
        Label(b, "menu.map.legend", b.t("map.legend"), (14, 354, 630, 76), parent=self.content.key, size=SECONDARY, color=MUTED)
        Label(b, "menu.map.position", b.t("map.position", x=f"{state[2].x:.1f}", y=f"{state[2].y:.1f}"),
              (14, 438, 620, 26), parent=self.content.key, size=SECONDARY, color=MUTED)

    def move(self, dx=0, dy=0):
        regions = self.query.regions()
        if regions:
            self.selection = (self.selection + dx) % len(regions)
            if dy:
                self.focused = dy < 0
            self.previous = None
            self.tick()

    def confirm(self):
        self.focused = not self.focused
        self.previous = None
        self.tick()
