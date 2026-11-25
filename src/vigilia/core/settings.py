"""Preferências TOML atômicas; JSON antigo continua legível e é preservado."""

import json
import math
import os
import tempfile
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path

from vigilia.core.config import Config
from vigilia.core.types import Action
from vigilia.core.locale import LANGUAGES


@dataclass(frozen=True, slots=True)
class UserOptions:
    config: Config
    language: str = "pt_BR"
    master_volume: float = .8
    music_volume: float = .7
    sfx_volume: float = 1
    hud_scale: float = 1.
    shake_strength: float = 1.
    high_contrast: bool = False


CONFIG_KEYS = ("width", "height", "vsync", "fullscreen", "shadow_quality", "draw_distance", "mouse_sensitivity", "ultrakill_style")
OPTION_KEYS = ("language", "master_volume", "music_volume", "sfx_volume", "hud_scale", "shake_strength", "high_contrast")
SECTIONS = {"graphics": CONFIG_KEYS[:6], "audio": ("master_volume", "music_volume", "sfx_volume"),
    "controls": ("mouse_sensitivity", "ultrakill_style"), "language": ("language",),
    "accessibility": ("hud_scale", "shake_strength", "high_contrast")}


class BindingConflict(ValueError):
    def __init__(self, actions):
        self.actions = tuple(actions)
        super().__init__("options.conflict")


class SettingsStore:
    def __init__(self, path: Path, defaults: Config, *, legacy_path: Path | None = None):
        self.path = Path(path)
        self.defaults = UserOptions(replace(defaults, bindings=defaults.bindings.copy(), gamepad=defaults.gamepad.copy()))
        self._validate(self.defaults)
        self.options = self.defaults
        source = self.path if self.path.is_file() else legacy_path if legacy_path and legacy_path.is_file() else None
        if source:
            if source.suffix.lower() == ".json":
                data = json.loads(source.read_text(encoding="utf-8"))
            else:
                nested = tomllib.loads(source.read_text(encoding="utf-8"))
                data = {key: value for section in SECTIONS for key, value in nested.get(section, {}).items()}
                data["bindings"] = data.get("bindings", {})
                data["gamepad"] = data.get("gamepad", {})
            if data.get("language") == "en":
                data["language"] = "en_US"
            config = replace(self.defaults.config, **{key: data[key] for key in CONFIG_KEYS if key in data},
                bindings=self.defaults.config.bindings | {Action(key): value for key, value in data.get("bindings", {}).items()},
                gamepad=self.defaults.config.gamepad | {Action(key): value for key, value in data.get("gamepad", {}).items()})
            self.options = replace(self.defaults, config=config, **{key: data[key] for key in OPTION_KEYS if key in data})
            self._validate(self.options)
            if source != self.path:
                self.save(self.options)  # Não altera o JSON de origem.

    @staticmethod
    def _validate(options):
        config = options.config
        if (type(config.width) is not int or type(config.height) is not int or config.width < 640 or config.height < 360
                or type(config.vsync) is not bool or type(config.mouse_sensitivity) not in (int, float) or not math.isfinite(config.mouse_sensitivity)
                or not .0001 <= config.mouse_sensitivity <= .02 or options.language not in LANGUAGES
                or type(config.fullscreen) is not bool or config.shadow_quality not in ("off", "low", "medium", "high")
                or type(config.draw_distance) not in (int, float) or not math.isfinite(config.draw_distance) or not 30 <= config.draw_distance <= 150
                or type(options.high_contrast) is not bool or type(config.ultrakill_style) is not bool
                or type(options.hud_scale) not in (int, float) or not math.isfinite(options.hud_scale) or not .8 <= options.hud_scale <= 1.4
                or type(options.shake_strength) not in (int, float) or not math.isfinite(options.shake_strength) or not 0 <= options.shake_strength <= 1
                or not all(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1 for value in
                           (options.master_volume, options.music_volume, options.sfx_volume))
                or not all(isinstance(value, str) and (value == "" or (value.strip() == value and all(value.split("-"))))
                           for value in (*config.bindings.values(), *config.gamepad.values()))):
            raise ValueError("options.invalid")

    def save(self, options: UserOptions):
        self._validate(options)
        config = options.config
        data = {key: getattr(config, key) for key in CONFIG_KEYS}
        data.update({key: getattr(options, key) for key in OPTION_KEYS})
        data["bindings"] = {key.value: value for key, value in config.bindings.items()}
        data["gamepad"] = {key.value: value for key, value in config.gamepad.items()}
        if self.path.suffix.lower() == ".json":
            content = json.dumps(data, ensure_ascii=False, indent=2)
        else:
            lines = ["# Preferências do jogador; capacidades detectadas não são gravadas."]
            for section, keys in SECTIONS.items():
                selected = {key: data[key] for key in keys if data[key] != getattr(self.defaults.config if key in CONFIG_KEYS else self.defaults, key)}
                if section == "controls":
                    for kind in ("bindings", "gamepad"):
                        changed = {key: value for key, value in data[kind].items() if value != getattr(self.defaults.config, kind).get(Action(key), "")}
                        if changed:
                            selected[kind] = changed
                if selected:
                    lines.extend(("", f"[{section}]"))
                    for key, value in selected.items():
                        if isinstance(value, dict):
                            lines.append(f"[{section}.{key}]")
                            lines.extend(f"{name} = {self._toml(value)}" for name, value in value.items())
                        else:
                            lines.append(f"{key} = {self._toml(value)}")
            content = "\n".join(lines) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent, suffix=".tmp", delete=False) as file:
                temporary = Path(file.name)
                file.write(content)
                file.flush()
                os.fsync(file.fileno())
            temporary.replace(self.path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
        self.options = options

    def set(self, key: str, value):
        if key in CONFIG_KEYS:
            candidate = replace(self.options, config=replace(self.options.config, **{key: value}))
        elif key in OPTION_KEYS:
            candidate = replace(self.options, **{key: value})
        else:
            raise ValueError("options.invalid")
        self.save(candidate)

    @staticmethod
    def _toml(value):
        return str(value).lower() if type(value) is bool else json.dumps(value, ensure_ascii=False)

    def conflicts(self, action, binding, *, device="keyboard"):
        mapping = self.options.config.gamepad if device == "gamepad" else self.options.config.bindings
        return tuple(key for key, value in mapping.items() if value and value == binding and key != Action(action))

    def rebind(self, action: str, binding: str, *, replace_conflicts=False, device="keyboard"):
        action = Action(action)
        if not isinstance(binding, str):
            raise ValueError("options.invalid")
        binding = binding.strip().lower().replace("ctrl", "control")
        if not binding or device not in ("keyboard", "gamepad"):
            raise ValueError("options.invalid")
        conflicts = self.conflicts(action, binding, device=device)
        if conflicts and not replace_conflicts:
            raise BindingConflict(conflicts)
        field = "gamepad" if device == "gamepad" else "bindings"
        mapping = getattr(self.options.config, field).copy()
        for other in conflicts:
            mapping[other] = ""
        mapping[action] = binding
        self.save(replace(self.options, config=replace(self.options.config,
             **{field: mapping})))

    def reset(self, category):
        if category == "all":
            self.save(self.defaults)
            return
        if category not in SECTIONS:
            raise ValueError("options.invalid")
        options, config = self.options, self.options.config
        config_changes = {key: getattr(self.defaults.config, key) for key in SECTIONS[category] if key in CONFIG_KEYS}
        option_changes = {key: getattr(self.defaults, key) for key in SECTIONS[category] if key in OPTION_KEYS}
        if category == "controls":
            config_changes.update(bindings=self.defaults.config.bindings.copy(), gamepad=self.defaults.config.gamepad.copy())
        self.save(replace(options, config=replace(config, **config_changes), **option_changes))
