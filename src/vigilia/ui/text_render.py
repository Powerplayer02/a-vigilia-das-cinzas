"""Tipografia única, resolvida pelo adaptador TextNode em engine/ui.py."""

from vigilia.core.protocols import IUIBackend
from vigilia.core.views import Color, Rect

SECONDARY, PRIMARY, TITLE, BOSS_NAME = 14, 20, 28, 44
INK: Color = (.94, .90, .79, 1)
MUTED: Color = (.64, .68, .68, 1)
GOLD: Color = (.91, .69, .32, 1)


def t(backend: IUIBackend, key: str, **values) -> str:
    return backend.t(key, **values)


def make_text(backend: IUIBackend, key: str, text: str, rect: Rect, *, parent=None,
              size=PRIMARY, color=INK) -> None:
    backend.create(key, "label", rect, parent=parent, text=text, size=size, color=color)
