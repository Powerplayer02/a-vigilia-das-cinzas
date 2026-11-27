"""Único adaptador nativo dos widgets. Layout em unidades de 1280×720."""

from collections.abc import Callable
from pathlib import Path
import unicodedata
import math

from direct.gui.DirectGui import DirectFrame, DirectButton, DirectEntry, DirectSlider
from direct.gui import DirectGuiGlobals as DGG
from direct.showbase.DirectObject import DirectObject
from panda3d.core import TextNode, Filename, LineSegs, Texture, TransparencyAttrib

from vigilia.core.views import Rect, Color
from vigilia.core.palette import PALETTE
from vigilia.engine.sprite_atlas import SpriteAtlas


def fallback_text(value: str) -> str:
    """Display-only ASCII equivalents for the engine's limited built-in font."""
    value = value.translate(str.maketrans({"×":"x", "·":"/", "—":"-", "–":"-", "→":"->", "←":"<-", "…":"..."}))
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")


class PandaUIBackend(DirectObject):
    def __init__(self, app, font_path: Path | None = None, *, localizer=None, capture_text=None, feedback=None) -> None:
        self.app = app
        self.root = app.aspect2d.attach_new_node("interface-4.5")
        self.root.set_bin("fixed", 30)
        self.nodes = {}
        self.labels = {}
        self.label_paths = {}
        self.parents = {}
        self.rects, self.outlines = {}, {}
        self.sprites, self.sprite_names = {}, {}
        self.atlas = SpriteAtlas(font_path.parent.parent / "ui_atlas" if font_path else None)
        self._transition_age = .15
        self._bar_targets = {}
        self._bar_active = set()
        self._panel_fades = {}
        self._closing_panels = []
        self.localizer = localizer
        self.capture_text = capture_text or (lambda active: None)
        self._feedback = feedback
        self._fallback_font = not (font_path and font_path.is_file())
        self.font = app.loader.loadFont(Filename.from_os_specific(str(font_path)).get_fullpath()) if not self._fallback_font else app.loader.loadFont("cmss12")
        if hasattr(self.font, "set_pixels_per_unit"):
            self.font.set_pixels_per_unit(96)
            self.font.set_minfilter(Texture.FT_linear_mipmap_linear)
            self.font.set_magfilter(Texture.FT_linear)
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
               value=0., minimum=0., maximum=1., sprite="") -> None:
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
                frameColor=PALETTE["surface"], thumb_frameColor=PALETTE["gold"],
                thumb_frameSize=(-7, 7, -height, 0), thumb_relief=DGG.FLAT)
            node["command"] = lambda: command(float(node["value"])) if command else None
        elif kind == "entry":
            node = DirectEntry(parent=owner, initialText=text, text_font=self.font,
                text_fg=PALETTE["ink"], width=max(1, (width - 20) / size), numLines=1, focus=0,
                scale=size, pos=(x + 8, 0, -y - size), frameColor=PALETTE["surface"],
                relief=DGG.FLAT, command=lambda value: self.focus_text(key, False),
                focusInCommand=lambda: self.capture_text(True), focusOutCommand=lambda: self.capture_text(False))
        elif kind == "panel":
            node = DirectFrame(parent=owner, frameSize=(0, width, -height, 0),
                               pos=(x, 0, -y), frameColor=color, relief=DGG.FLAT, borderWidth=(0, 0), state=DGG.DISABLED)
        else:
            node = owner.attach_new_node(key)
            node.set_pos(x, 0, -y)
        self.nodes[key] = node
        if kind=='panel' and parent is None and width>=600 and height>=300:
            node.set_transparency(TransparencyAttrib.M_alpha)
            node.set_alpha_scale(0)
            self._panel_fades[key]=0.
        if kind == "sprite":
            self.sprites[key] = self.atlas.attach(node, sprite, (0, 0, width, height))
            self.sprite_names[key] = sprite
        elif kind in ("panel", "button") and width >= 96 and height >= 32 and color[3] >= .9:
            self.atlas.attach(node, "button" if kind == "button" else "panel", (0, 0, width, height), frame=True)
        if kind == "button" and sprite and width >= 120 and height >= 40:
            side = min(26, height - 8)
            self.atlas.attach(node, sprite, (10, (height-side)/2, side, side))
        if kind == "button":
            line = LineSegs("focus-outline")
            line.set_color(*PALETTE["gold"])
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
            label.set_text(fallback_text(text) if self._fallback_font else text)
            label.set_align(TextNode.A_left)
            inset = 44 if kind == "button" and sprite and width >= 120 and height >= 40 else 10 if kind == "button" else 0
            label.set_wordwrap(max(1, (width - inset - 8) / size))
            label.set_text_color(*(color if kind == "label" else PALETTE["ink"]))
            label.set_shadow(.05, .07)
            label.set_shadow_color(0, 0, 0, .7)
            path = node.attach_new_node(label)
            path.set_scale(size)
            path.set_pos(inset, -.01, -size)
            self.labels[key] = label
            self.label_paths[key] = path

    def text(self, key: str, value: str) -> None:
        if isinstance(self.nodes[key], DirectEntry):
            self.nodes[key].enterText(value)
        else:
            self.labels[key].set_text(fallback_text(value) if self._fallback_font else value)

    def set_sprite(self, key, sprite):
        if self.sprite_names.get(key) == sprite:
            return
        self.sprites[key].remove_node()
        width, height = self.rects[key][2:]
        self.sprites[key] = self.atlas.attach(self.nodes[key], sprite, (0, 0, width, height))
        self.sprite_names[key] = sprite

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
        value=max(.00001,min(1,value))
        if key not in self._bar_targets:self.nodes[key].set_sx(value)
        else:self._bar_active.add(key)
        self._bar_targets[key]=value

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
            self.nodes[key].set_color_scale((1.08,1.06,1.02,1) if value else (1,1,1,1))

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
        weight=1-math.exp(-max(0,dt)/.055)
        for key in tuple(self._bar_active):
            node=self.nodes[key];target=self._bar_targets[key]
            value=node.get_sx()+(target-node.get_sx())*weight
            if abs(value-target)<.001:value=target;self._bar_active.remove(key)
            node.set_sx(value)
        for key in tuple(self._panel_fades):
            age=self._panel_fades[key]+max(0,dt);self._panel_fades[key]=age
            t=min(1,age/.15);self.nodes[key].set_alpha_scale(t*t*(3-2*t))
            if t==1:del self._panel_fades[key]
        for entry in tuple(self._closing_panels):
            entry[1]+=max(0,dt);t=min(1,entry[1]/.15)
            entry[0].set_alpha_scale(entry[2]*(1-t*t*(3-2*t)))
            if t==1:entry[0].remove_node();self._closing_panels.remove(entry)

    def destroy(self, key: str) -> None:
        rect=self.rects.get(key)
        if self.parents.get(key) is None and rect and rect[2]>=600 and rect[3]>=300 and not self.nodes[key].is_hidden():
            copy=self.nodes[key].copy_to(self.root)
            copy.set_transparency(TransparencyAttrib.M_alpha)
            for item in copy.find_all_matches('**/+PGItem'):item.node().set_active(False)
            if hasattr(copy.node(),'set_active'):copy.node().set_active(False)
            self._closing_panels.append([copy,0.,copy.get_color_scale().w])
        for child in [name for name, parent in self.parents.items() if parent == key]:
            self.destroy(child)
        node = self.nodes.pop(key)
        if isinstance(node, DirectEntry) and node["focus"]:
            self.capture_text(False)
        node.destroy() if isinstance(node, (DirectFrame, DirectButton, DirectEntry, DirectSlider)) else node.remove_node()
        self.parents.pop(key)
        self.labels.pop(key, None)
        self.label_paths.pop(key, None)
        self.outlines.pop(key, None)
        self.rects.pop(key, None)
        self.sprites.pop(key, None)
        self.sprite_names.pop(key, None)
        self._bar_active.discard(key);self._bar_targets.pop(key,None);self._panel_fades.pop(key,None)

    def close(self) -> None:
        self.ignoreAll()
        for key in [name for name, parent in self.parents.items() if parent is None]:
            self.destroy(key)
        self.root.remove_node()
        for node,*_ in self._closing_panels:node.remove_node()
        self._closing_panels.clear()
