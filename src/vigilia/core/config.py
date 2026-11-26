"""Configuração TOML da arena e dos controles."""

import math
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from vigilia.core.types import Action

DEFAULT_KEYMAP = {
    Action.MOVE_FORWARD: "w",
    Action.MOVE_BACK: "s",
    Action.MOVE_LEFT: "a",
    Action.MOVE_RIGHT: "d",
    Action.RUN: "shift",
    Action.ROLL: "space",
    Action.DASH: "alt",
    Action.SLIDE: "v",
    Action.JUMP: "b",
    Action.SLAM: "g",
    Action.LOCK_ON: "q",
    Action.PAUSE: "escape",
    Action.LIGHT: "mouse1",
    Action.HEAVY: "mouse3",
    Action.BLOCK: "control",
    Action.PARRY: "r",
    Action.CAST: "e",
    Action.SWAP_WEAPON: "1",
    Action.RESET_ARENA: "f5",
    Action.INTERACT: "f",
    Action.SAVE: "f8",
    Action.LOAD: "f9",
    Action.RELOAD_BOSS: "f7",
    Action.OPEN_INVENTORY: "i",
    Action.OPEN_STATUS: "c",
    Action.OPEN_LEVEL_UP: "l",
    Action.TRAVEL: "f6",
    Action.UPGRADE: "u",
    Action.LEVEL_VIGOR: "2",
    Action.LEVEL_ENDURANCE: "3",
    Action.LEVEL_STRENGTH: "4",
    Action.LEVEL_DEXTERITY: "5",
    Action.LEVEL_INTELLIGENCE: "6",
    Action.LEVEL_FAITH: "7",
    Action.LEVEL_LUCK: "8",
    Action.TARGET_LEFT: "z",
    Action.TARGET_RIGHT: "x",
}
DEFAULT_PADMAP = {
    Action.RUN: "lstick",
    Action.ROLL: "face_a",
    Action.LOCK_ON: "rstick",
    Action.PAUSE: "start",
    Action.LIGHT: "rshoulder",
    Action.HEAVY: "right_trigger",
    Action.BLOCK: "lshoulder",
    Action.PARRY: "face_b",
    Action.CAST: "left_trigger",
    Action.SWAP_WEAPON: "face_y",
    Action.RESET_ARENA: "back",
    Action.INTERACT: "face_x",
    Action.DASH: "dpad_right",
    Action.SLIDE: "dpad_down",
    Action.JUMP: "dpad_up",
    Action.SLAM: "dpad_left",
}


@dataclass(slots=True)
class Config:
    width: int = 1280
    height: int = 720
    mouse_sensitivity: float = 0.003
    bindings: dict[Action, str] = field(default_factory=lambda: DEFAULT_KEYMAP.copy())
    gamepad: dict[Action, str] = field(default_factory=lambda: DEFAULT_PADMAP.copy())
    vsync: bool = True
    fullscreen: bool = False
    shadow_quality: str = "medium"
    draw_distance: float = 100.
    ultrakill_style: bool = False
    procedural_music: bool = False


def _bindings(data: dict, key: str, defaults: dict[Action, str]) -> dict[Action, str]:
    bindings = defaults.copy()
    for name, value in data.get(key, {}).items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Binding inválido em [{key}]: {name}")
        bindings[Action(name)] = value.strip().lower()
    return bindings


def load_config(path: Path) -> Config:
    """Lê a configuração e permite sobrescrever a janela por ambiente."""
    with path.open("rb") as file:
        data = tomllib.load(file)
    window = data.get("window", {})
    width = int(os.getenv("VIGILIA_WIDTH", window.get("width", 1280)))
    height = int(os.getenv("VIGILIA_HEIGHT", window.get("height", 720)))
    sensitivity = float(data.get("camera", {}).get("mouse_sensitivity", 0.003))
    if width < 640 or height < 360 or not math.isfinite(sensitivity) or sensitivity <= 0:
        raise ValueError("A janela deve ter ao menos 640×360 e a sensibilidade deve ser positiva.")
    vsync = window.get("vsync", True)
    if type(vsync) is not bool:
        raise ValueError("window.vsync precisa ser true ou false.")
    graphics = data.get("graphics", {})
    agile = data.get("movement", {}).get("ultrakill_style", False)
    if type(agile) is not bool:
        raise ValueError("movement.ultrakill_style precisa ser true ou false.")
    music = data.get("audio", {}).get("procedural_music", False)
    if type(music) is not bool:
        raise ValueError("audio.procedural_music precisa ser true ou false.")
    return Config(width, height, sensitivity,
                  _bindings(data, "bindings", DEFAULT_KEYMAP),
                  _bindings(data, "gamepad", DEFAULT_PADMAP), vsync,
                  window.get("fullscreen", False), graphics.get("shadow_quality", "medium"),
                  graphics.get("draw_distance", 100.), agile, music)
