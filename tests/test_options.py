"""Persistência atômica e captura de remapeamento fora do gameplay."""

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from ui_fakes import BackendFake, ActionsFake
from vigilia.core.config import Config, DEFAULT_KEYMAP
from vigilia.core.settings import SettingsStore
from vigilia.core.locale import Localizer
from vigilia.core.types import Action
from vigilia.core.views import OptionView
from vigilia.core.settings import BindingConflict, UserOptions
from vigilia.core.events import EventBus, SettingsChangedEvent
from vigilia.engine.audio import AudioEventRouter, AudioBackend
from vigilia.engine.input import InputManager, InputMode
from vigilia.ui.options_ui import OptionsUI


def test_options_reopen_with_locale_graphics_volumes_and_rebound_key(tmp_path):
    path = tmp_path / "options.json"
    store = SettingsStore(path, Config())
    store.set("language", "en_US")
    store.set("width", 1600)
    store.set("music_volume", .2)
    store.rebind("reset_arena", "f4")
    loaded = SettingsStore(path, Config()).options
    assert loaded.language == "en_US" and loaded.config.width == 1600
    assert loaded.music_volume == .2 and loaded.config.bindings[Action.RESET_ARENA] == "f4"
    before = path.read_bytes()
    for key, value in (("width", 10), ("language", "xx"), ("sfx_volume", float("nan")), ("mouse_sensitivity", "fast")):
        with pytest.raises(ValueError):
            store.set(key, value)
    assert path.read_bytes() == before and not list(tmp_path.glob("*.tmp"))


def test_control_pages_are_accessible_with_directional_navigation_and_capture_cancels():
    backend, actions, source = BackendFake(), ActionsFake(), InputManager()
    rows = tuple(OptionView(action.value, action.value, binding) for action, binding in DEFAULT_KEYMAP.items())
    query = SimpleNamespace(option_rows=lambda category: rows if category == "controls" else (OptionView("vsync", "VSync", "On"),))
    source.set_mode(InputMode.MENU)
    screen = OptionsUI(backend, query, actions, source)
    screen.select_category(2)
    for _ in range(8):
        screen.move(dy=1)
    assert screen.page == 1 and screen.grid.index == 0
    screen.confirm()
    source.key("escape", True)
    assert source.menu_next_edge() is None
    screen.tick()
    assert screen.capture is None and not actions.commands
    source.key("escape", False)
    screen.confirm()
    source.key("f4", True)
    screen.tick()
    assert json.loads(actions.commands[-1].argument)["binding"] == "f4"
    assert source.next_edge() is None


def test_both_locales_have_matching_keys_and_hud_templates():
    from string import Formatter
    directory = Path(__file__).resolve().parents[1] / "data/locale"
    pt, en = Localizer(directory), Localizer(directory, "en_US")
    assert pt.catalog.keys() == en.catalog.keys()
    assert "VITALIDADE" in pt.t("hud.hp", value=70, maximum=140)
    assert "HEALTH" in en.t("hud.hp", value=70, maximum=140)
    assert en.t("class.mage.name") == "Mage"
    for key in pt.catalog:
        fields = lambda text: {name for _, name, _, _ in Formatter().parse(text) if name is not None}
        assert fields(pt.catalog[key]) == fields(en.catalog[key]), key


def test_binding_capture_ignores_launch_key_autorepeat_and_mouse_click():
    source = InputManager()
    source.set_mode(InputMode.MENU)
    source.key("enter", True)
    source.begin_binding_capture()
    source.key("enter", True)
    source.key("mouse1", True)
    assert source.captured_binding() is None
    source.key("f4", True)
    assert source.captured_binding() == "f4"


def test_user_toml_only_stores_overrides_and_migrates_json_without_touching_source(tmp_path):
    import tomllib
    legacy = tmp_path / "options.json"
    legacy.write_text(json.dumps(dict(language="en", music_volume=.2, bindings={"cast": "f4"})))
    original = legacy.read_bytes()
    path = tmp_path / "settings.toml"
    store = SettingsStore(path, Config(), legacy_path=legacy)
    assert legacy.read_bytes() == original and store.options.language == "en_US"
    parsed = tomllib.loads(path.read_text(encoding="utf-8"))
    assert parsed == dict(language=dict(language="en_US"), audio=dict(music_volume=.2), controls=dict(bindings=dict(cast="f4")))
    store.set("hud_scale", 1.4)
    store.set("fullscreen", True)
    store.set("shadow_quality", "high")
    loaded = SettingsStore(path, Config()).options
    assert loaded == store.options and loaded.config.fullscreen and loaded.hud_scale == 1.4
    assert "desktop" not in path.read_text() and "capabilities" not in path.read_text()


def test_resets_keep_other_tabs_and_conflicting_keyboard_or_gamepad_binding_requires_confirmation(tmp_path):
    store = SettingsStore(tmp_path / "settings.toml", Config())
    store.set("master_volume", 0)
    store.set("hud_scale", 1.4)
    for device, target, old, binding in (("keyboard", Action.CAST, Action.INTERACT, "f"),
                                       ("gamepad", Action.CAST, Action.ROLL, "face_a")):
        before = store.options
        with pytest.raises(BindingConflict):
            store.rebind(target, binding, device=device)
        assert store.options == before
        store.rebind(target, binding, device=device, replace_conflicts=True)
        mapping = store.options.config.gamepad if device == "gamepad" else store.options.config.bindings
        assert mapping[target] == binding and mapping[old] == ""
    store.reset("controls")
    assert store.options.config.bindings == Config().bindings and store.options.config.gamepad == Config().gamepad
    assert store.options.master_volume == 0 and store.options.hud_scale == 1.4
    store.reset("accessibility")
    assert store.options.hud_scale == 1 and store.options.master_volume == 0
    store.reset("all")
    assert store.options == UserOptions(Config()) == SettingsStore(store.path, Config()).options


def test_master_zero_reaches_playing_music_synchronously_through_settings_event(tmp_path):
    from test_audio import MixerFake
    folder = tmp_path / "audio/music"
    folder.mkdir(parents=True)
    (folder / "track.wav").write_bytes(b"fake")
    mixer = MixerFake()
    backend = AudioBackend(tmp_path, mixer=mixer)
    bus = EventBus()
    AudioEventRouter(bus, backend, tmp_path / "unused.toml")
    backend.play_music("track", fade_sec=0)
    backend.update(0)
    assert any(channel.get_busy() and max(channel.volume) > 0 for channel in backend._music)
    bus.publish(SettingsChangedEvent(UserOptions(Config(), master_volume=0), ("master_volume",)))
    assert all(not any(channel.volume) for channel in backend._music)  # Sem update/tick entre evento e assert.
    backend.close()


def test_reset_all_cancel_and_conflict_cancel_dispatch_no_mutation():
    backend, actions, source = BackendFake(), ActionsFake(), InputManager()
    query = SimpleNamespace(option_rows=lambda category: (OptionView("cast", "Conjurar", "E"),),
        binding_conflicts=lambda *args: ("Interagir",))
    source.set_mode(InputMode.MENU)
    screen = OptionsUI(backend, query, actions, source)
    screen.reset_all()
    screen.confirm()
    assert screen.modal is None and not actions.commands
    screen.select_category(2)
    screen.confirm()
    source.key("f", True)
    screen.tick()
    assert screen.modal is not None and screen.modal.grid.index == 0
    screen.confirm()
    assert screen.modal is None and not actions.commands


def test_mouse_and_gamepad_capture_are_armed_after_launch_input_is_released():
    source = InputManager()
    source.set_mode(InputMode.MENU)
    source.key("mouse1", True)
    source.begin_binding_capture()
    source.arm_mouse_capture()
    source.key("mouse1", False)
    source.key("mouse2", True)
    assert source.captured_binding() == "mouse2"
    source.poll_gamepad(frozenset({"face_a"}), 0., 0.)
    source.begin_binding_capture("gamepad")
    source.poll_gamepad(frozenset({"face_a"}), 0., 0.)
    assert source.captured_binding() is None
    source.poll_gamepad(frozenset({"face_x"}), 0., 0.)
    assert source.captured_binding() == "face_x"
