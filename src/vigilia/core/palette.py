"""One presentation palette, also available when data/assets are absent."""

from pathlib import Path
from types import MappingProxyType
import math
import tomllib

DEFAULTS = {
    "ink": (.94, .90, .79, 1.), "muted": (.64, .68, .68, 1.),
    "gold": (.91, .69, .32, 1.), "border": (.50, .40, .25, 1.),
    "panel": (.035, .047, .055, .96), "surface": (.075, .09, .10, .98),
    "focus": (.24, .19, .105, 1.), "veil": (.012, .018, .025, .85),
    "hp": (.72, .19, .13, 1.), "stamina": (.38, .66, .44, 1.),
    "mana": (.34, .66, .83, 1.), "danger": (.34, .055, .04, 1.),
    "danger_focus": (.56, .10, .065, 1.),
}


def load_palette(path: Path):
    if not path.is_file():
        return MappingProxyType(DEFAULTS.copy())
    document = tomllib.loads(path.read_text(encoding="utf8"))
    if document.get("version") != 1:
        raise ValueError("Unsupported UI palette version")
    colors = DEFAULTS.copy()
    for key, value in document.get("colors", {}).items():
        if key not in colors or not isinstance(value, list) or len(value) != 4 or any(
            isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 1 for v in value
        ):
            raise ValueError(f"Invalid palette color: {key}")
        colors[key] = tuple(float(v) for v in value)
    return MappingProxyType(colors)


PALETTE = load_palette(Path(__file__).resolve().parents[3] / "data/palette.toml")
