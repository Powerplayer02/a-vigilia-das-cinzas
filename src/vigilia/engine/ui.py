"""Único adaptador nativo dos widgets. Layout em unidades de 1280×720."""

from collections.abc import Callable
from pathlib import Path

from direct.gui.DirectGui import DirectFrame, DirectButton, DirectEntry, DirectSlider
from direct.gui import DirectGuiGlobals as DGG
from direct.showbase.DirectObject import DirectObject
from panda3d.core import TextNode, Filename, LineSegs

from vigilia.core.views import Rect, Color


class PandaUIBackend(DirectObject):
    def __init__(self, app, font_path: Path | None = None, *, localizer=None, capture_text=None, feedback=None) -> None:
        self.app = app
        self.root = app.aspect2d.attach_new_node("interface-4.5")
        self.root.set_bin("fixed", 30)
        self.nodes = {}
        self.labels = {}
        self.parents = {}
        self.rects, self.outlines = {}, {}
        self._transition_age = .15
        self.localizer = localizer
        self.capture_text = capture_text or (lambda active: None)
        self._feedback = feedback
        self.font = app.loader.loadFont(Filename.from_os_specific(str(font_path)).get_fullpath()) if font_path and font_path.is_file() else app.loader.loadFont("cmss12")
        if hasattr(self.font, "set_pixels_per_unit"):
            self.font.set_pixels_per_unit(48)
        self.accept("aspectRatioChanged", self._layout)
        self._layout()

    def t(self, key, **values):
        return self.localizer.t(key, **values)

    def feedback(self, kind):
        if self._feedback is not None:
            self._feedback(kind)

    def _layout(self) -> None:
        scale = min(2 / 720, 2 * self.app.getAspectRatio() / 1280)
        self.root.set_scale(scale)
        self.root.set_pos(-640 * scale, 0, 360 * scale)

    def create(self, key: str, kind: str, rect: Rect, *, parent=None, text="", size=20,
               color: Color = (1, 1, 1, 1), command: Callable[..., None] | None = None,
               value=0., minimum=0., maximum=1.) -> None:
        if key in self.nodes:
            raise ValueError(f"Widget duplicado: {key}")
        x, y, width, height = rect
        owner = self.root if parent is None else self.nodes[parent]
        self.parents[key] = parent
        self.rects[key] = rect
        if kind == "button":
            node = DirectButton(parent=owner, frameSize=(0, width, -height, 0),
                                pos=(x, 0, -y), frameColor=color, relief=DGG.FLAT, borderWidth=(0, 0), command=command)
            node.bind(DGG.ENTER, lambda event: self.feedback("ui_hover"))
        elif kind == "slider":
            node = DirectSlider(parent=owner, range=(minimum, maximum), value=value, pageSize=(maximum - minimum) / 10,
                frameSize=(0, width, -height, 0), pos=(x, 0, -y), scale=1,
                frameColor=(.15, .17, .19, 1), thumb_frameColor=(.9, .7, .3, 1),
                thumb_frameSize=(-7, 7, -height, 0), thumb_relief=DGG.FLAT)
            node["command"] = lambda: command(float(node["value"])) if command else None
        elif kind == "entry":
            node = DirectEntry(parent=owner, initialText=text, text_font=self.font,
                text_fg=(.94, .88, .75, 1), width=max(1, (width - 20) / size), numLines=1, focus=0,
                scale=size, pos=(x + 8, 0, -y - size), frameColor=(.08, .10, .12, 1),
                relief=DGG.FLAT, command=lambda value: self.focus_text(key, False),
                focusInCommand=lambda: self.capture_text(True), focusOutCommand=lambda: self.capture_text(False))
        elif kind == "panel":
            node = DirectFrame(parent=owner, frameSize=(0, width, -height, 0),
                               pos=(x, 0, -y), frameColor=color, relief=DGG.FLAT, borderWidth=(0, 0), state=DGG.DISABLED)
        else:
            node = owner.attach_new_node(key)
            node.set_pos(x, 0, -y)
        self.nodes[key] = node
        if kind == "button":
            line = LineSegs("focus-outline")
            line.set_color(.95, .72, .3, 1)
            line.set_thickness(2)
            line.move_to(0, -.03, 0)
            for point in ((width, -.03, 0), (width, -.03, -height), (0, -.03, -height), (0, -.03, 0)):
                line.draw_to(*point)
            outline = node.attach_new_node(line.create())
            outline.hide()
            self.outlines[key] = outline
        if kind in ("label", "button"):
            label = TextNode(key + "-text")
            label.set_font(self.font)
            label.set_text(text)
            label.set_align(TextNode.A_left)
            label.set_wordwrap(max(1, (width - 12) / size))
            label.set_text_color(*(color if kind == "label" else (.94, .88, .75, 1)))
            label.set_shadow(.05, .07)
            label.set_shadow_color(0, 0, 0, .7)
            path = node.attach_new_node(label)
            path.set_scale(size)
            path.set_pos(10 if kind == "button" else 0, -.01, -size)
            self.labels[key] = label

    def text(self, key: str, value: str) -> None:
        if isinstance(self.nodes[key], DirectEntry):
            self.nodes[key].enterText(value)
        else:
            self.labels[key].set_text(value)

    def read_text(self, key):
        return self.nodes[key].get()

    def focus_text(self, key, value):
        self.nodes[key]["focus"] = int(value)
        self.capture_text(value)

    def text_active(self):
        return any(isinstance(node, DirectEntry) and node["focus"] for node in self.nodes.values())

    def visible(self, key: str, value: bool) -> None:
        self.nodes[key].show() if value else self.nodes[key].hide()

    def fraction(self, key: str, value: float) -> None:
        self.nodes[key].set_sx(max(.00001, min(1, value)))

    def color(self, key: str, value: Color) -> None:
        node = self.nodes[key]
        if isinstance(node, (DirectFrame, DirectButton)):
            node["frameColor"] = value
        else:
            self.labels[key].set_text_color(*value)

    def enabled(self, key: str, value: bool) -> None:
        if isinstance(self.nodes[key], DirectButton):
            self.nodes[key]["state"] = DGG.NORMAL if value else DGG.DISABLED

    def focus_outline(self, key, value):
        if key in self.outlines:
            self.outlines[key].show() if value else self.outlines[key].hide()

    def scale_at(self, key, value, anchor):
        x, y, width, height = self.rects[key]
        if "right" in anchor:
            x = 1280 - (1280 - x - width) - width * value
        elif "center" in anchor or anchor == "top_message":
            x = (1280 - width * value) / 2
        if anchor.startswith("bottom"):
            y = 720 - (720 - y - height) - height * value
        elif anchor == "top_center":
            y = 24
        elif anchor == "top_message":
            y = 128
        self.nodes[key].set_scale(value)
        self.nodes[key].set_pos(x, 0, -y)

    def transition(self):
        self._transition_age = 0.
        self.root.set_alpha_scale(0)

    def tick(self, dt):
        if self._transition_age < .15:
            self._transition_age += max(0, dt)
            self.root.set_alpha_scale(min(1, self._transition_age / .15))

    def destroy(self, key: str) -> None:
        for child in [name for name, parent in self.parents.items() if parent == key]:
            self.destroy(child)
        node = self.nodes.pop(key)
        if isinstance(node, DirectEntry) and node["focus"]:
            self.capture_text(False)
        node.destroy() if isinstance(node, (DirectFrame, DirectButton, DirectEntry, DirectSlider)) else node.remove_node()
        self.parents.pop(key)
        self.labels.pop(key, None)
        self.outlines.pop(key, None)
        self.rects.pop(key, None)

    def close(self) -> None:
        self.ignoreAll()
        for key in [name for name, parent in self.parents.items() if parent is None]:
            self.destroy(key)
        self.root.remove_node()
