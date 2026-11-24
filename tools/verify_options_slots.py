"""Aceite nativo 5.2b: modais, opções por evento, HUD e prefs em TOML."""

import argparse
from contextlib import ExitStack
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from panda3d.core import Filename
from vigilia.core.config import Config
from vigilia.core.events import SettingsChangedEvent
from vigilia.core.types import AppState as S, Action
from vigilia.core.views import UICommand, UICommandKind as C
from vigilia.engine.app import ArenaApp
from vigilia.game import Game


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/5.2b")
    output = parser.parse_args().output
    output.mkdir(parents=True, exist_ok=True)
    app = ArenaApp(Config(vsync=False), window_type="offscreen")
    try:
        with tempfile.TemporaryDirectory(prefix="vigilia-options-qa-") as directory, ExitStack() as cleanup:
            base = Path(directory)
            game = Game(app, Config(vsync=False), ROOT / "assets", front_end=True, enemy_count=3,
                save_path=base / "slots.sqlite3", settings_path=base / "settings.toml")
            cleanup.callback(game.close)
            app.start(game)
            app.taskMgr.remove("vigilia-update")
            events = []
            game._bus.subscribe(SettingsChangedEvent, events.append)

            def frames(count=12):
                for _ in range(count):
                    game.frame(1 / 60, (0, 0), (0, 0))

            def capture(name):
                frames()
                for _ in range(2):
                    app.graphicsEngine.render_frame()
                assert app.win.save_screenshot(Filename.from_os_specific(str(output / (name + ".png"))))

            def command(kind, arg=""):
                result = game.execute(UICommand(kind, arg))
                assert not result.startswith(game.localizer.t("common.error", error="")), result
                return result

            def option(key, value=None):
                data = dict(key=key)
                if value is not None:
                    data["value"] = value
                return command(C.SET_OPTION, json.dumps(data))

            for slot, class_index in ((1, 0), (2, 3), (3, 4)):
                command(C.NEW_GAME)
                assert game.flow.current == S.SLOT_SELECT
                command(C.SELECT_NEW_SLOT, str(slot))
                screen = game.front.screen
                screen.select_class(class_index)
                for _ in range(10):
                    screen.adjust("vigor", 1)
                screen.create()
                assert game.flow.current == S.PLAYING and game.active_slot == slot
                frames()
                command(C.MAIN_MENU)

            snapshot = game._save.load(3)
            game._save.save(3, replace(snapshot, player=replace(snapshot.player, bloodstain_souls=187, bloodstain_position=snapshot.player.motion.position)))
            preserved = {slot: game._save.load(slot) for slot in (1, 2)}
            command(C.CONTINUE)
            slots = game.front.screen
            slots.request_delete(3)
            capture("delete-review-pt")
            slots.confirm()  # Cancelar, nunca o repositório.
            assert game._save.load(3) is not None
            slots.request_delete(3)
            slots.move(dx=1)
            slots.confirm()
            assert slots.stage == 1 and slots.modal.grid.index == 0
            capture("delete-final-pt")
            slots.confirm()
            assert game._save.load(3) is not None
            slots.request_delete(3)
            slots.move(dx=1)
            slots.confirm()
            option("language")
            frames(1)
            assert game.ui_backend.labels["front.delete.3"].get_text() == "Delete"
            assert "Souls at" in game.ui_backend.labels["front.modal.body"].get_text()
            capture("delete-final-en")
            root = slots.root
            slots.move(dx=1)
            slots.confirm()
            assert slots.root is root and game._save.load(3) is None
            assert all(game._save.load(slot) == snap for slot, snap in preserved.items())
            capture("slots-refreshed-en")

            command(C.OPEN_OPTIONS)
            screen = game.front.screen
            capture("options-graphics-en")
            screen.select_category(1)
            assert len([key for key in game.ui_backend.nodes if key.startswith("front.slider.")]) == 3
            frames(100)  # Música de menu tocando antes de mutar.
            assert game._audio.enabled and any(channel.get_busy() and channel.get_volume() > 0 for channel in game._audio._music)
            slider = game.ui_backend.nodes["front.slider.master_volume"]
            slider["value"] = 0
            slider["command"]()  # Mesmo callback nativo do arraste, sem tick de áudio intermediário.
            assert game._audio.master_volume == 0
            assert all(channel.get_volume() == 0 for channel in game._audio._music)
            assert events[-1].changed == ("master_volume",)
            capture("options-audio-en")
            screen.reset_tab()
            assert (game._audio.master_volume, game._audio.sfx_volume, game._audio.music_volume) == (.8, 1., .7)
            screen.select_category(2)
            # E agora é confirmação de menu, além de conjurar no gameplay.
            cast_index = next(i for i, row in enumerate(game.queries.option_rows("controls")) if row.id == "cast")
            screen.page = cast_index // 8
            screen.render(focus=cast_index % 8)
            screen.confirm()
            game.keyboard("f", True)
            frames(1)
            game.keyboard("f", False)
            assert screen.modal is not None and screen.modal.grid.index == 0
            capture("binding-conflict-en")
            screen.modal.move(dx=1)
            screen.modal.confirm()
            assert game._bindings[Action.CAST] == "f" and game._bindings[Action.INTERACT] == ""
            screen.reset_tab()
            assert game._bindings[Action.CAST] == "e" and game._bindings[Action.INTERACT] == "f"
            screen.toggle_device()
            capture("controls-gamepad-en")
            screen.select_category(4)
            screen.set_slider(0, 1.4)
            screen.set_slider(1, 0)
            screen.change(2, 1)
            assert game._polish.strength == 0 and game.settings.options.high_contrast
            capture("options-accessibility-en")
            command(C.BACK)
            assert game.flow.current == S.SLOT_SELECT
            command(C.LOAD_SLOT, "2")
            frames()
            assert "stamina" in game.ui_backend.labels["hud.spell.info"].get_text()
            assert game.ui_backend.labels["hud.spell.glyph"].get_text() == "*"
            capture("hud-mage-large-contrast-en")
            for quality in ("off", "low", "medium", "high"):
                game.settings.set("shadow_quality", quality)
                game._bus.publish(SettingsChangedEvent(game.settings.options, ("shadow_quality",)))
                frames(1)
                assert game._renderer.shadows.quality == quality
            option("draw_distance")
            assert app.camLens.get_far() == 140
            command(C.MAIN_MENU)
            command(C.OPEN_OPTIONS)
            screen = game.front.screen
            screen.reset_all()
            assert screen.modal.grid.index == 0
            screen.modal.move(dx=1)
            screen.modal.confirm()
            assert game.localizer.language == "pt_BR" and game.settings.options.hud_scale == 1
            assert not tomllib.loads((base / "settings.toml").read_text(encoding="utf-8"))
            capture("options-reset-pt")
            report = dict(result="ok", double_cancel_preserves_slot=True, double_accept_hard_deletes=True,
                surviving_slots_unchanged=True, list_refreshed_without_rebuild=True, locale_latency_frames=1,
                native_sliders=3, master_zero_muted_music_synchronously=True, settings_events=len(events),
                conflict_confirmation=True, resets_tab_and_global=True, gamepad="simulated only; no physical controller",
                hud_scale=1.4, high_contrast=True, shake_disabled=True, contact_shadow_qualities=4,
                capabilities_not_persisted=True, user_preferences=str("data/settings.toml"))
            (output / "options-slots.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            game.close()
            print(json.dumps(report, ensure_ascii=False))
    finally:
        app.destroy()


if __name__ == "__main__":
    main()
