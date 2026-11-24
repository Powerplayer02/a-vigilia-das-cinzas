"""Percurso nativo da 4.5.2 em um único aplicativo e banco temporário."""

import argparse
from contextlib import ExitStack
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from panda3d.core import Filename, InputDevice
from vigilia.core.config import Config
from vigilia.core.types import AppState as S
from vigilia.core.views import UICommand, UICommandKind as C
from vigilia.core.events import SaveRequestedEvent, AreaEnteredEvent
from vigilia.core.mathx import Vec3, Transform
from vigilia.core.settings import SettingsStore
from vigilia.engine.app import ArenaApp
from vigilia.game import Game


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/4.5.2")
    output = parser.parse_args().output
    output.mkdir(parents=True, exist_ok=True)
    config = Config(vsync=False)
    app = ArenaApp(config, window_type="offscreen")
    try:
        with tempfile.TemporaryDirectory(prefix="vigilia-front-qa-") as temporary, ExitStack() as cleanup:
            database = Path(temporary) / "slots.sqlite3"
            options_path = Path(temporary) / "options.json"
            game = Game(app, config, ROOT / "assets", save_path=database, settings_path=options_path,
                        front_end=True, enemy_count=3)
            cleanup.callback(game.close)
            app.start(game)
            app.taskMgr.remove("vigilia-update")

            def advance(count=1):
                for _ in range(count):
                    game.frame(1 / 60, (0, 0), (0, 0))

            def tap(key):
                game.keyboard(key, True)
                advance()
                game.keyboard(key, False)
                advance()

            def capture(name):
                advance()
                for _ in range(2):
                    app.graphicsEngine.renderFrame()
                assert app.win.save_screenshot(Filename.from_os_specific(str(output / name)))

            assert game.flow.current == S.MAIN_MENU
            advance(60)
            assert game.ai.step == 0 and not game._save.list()
            capture("main-menu.png")
            for slot, class_index, name in ((1, 0, "Vésper"), (2, 4, "Vera"), (3, 3, "Lume")):
                tap("enter")
                assert game.flow.current == S.SLOT_SELECT
                game.execute(UICommand(C.SELECT_NEW_SLOT, str(slot)))
                assert game.flow.current == S.CHARACTER_CREATION
                screen = game.front.screen
                screen.select_class(class_index)
                game.ui_backend.text("front.name", name)
                screen.entry.focus()
                game.keyboard("w", True)
                advance()
                assert game.front.screen.class_index == class_index
                tap("escape")
                game.keyboard("w", False)
                assert game.flow.current == S.CHARACTER_CREATION
                for _ in range(10):
                    screen.adjust("vigor", 1)
                capture(f"character-{slot}.png")
                screen.create()
                assert game.flow.current == S.PLAYING and game.active_slot == slot
                assert game.character_name == name and game._save.load(slot).player.character_name == name
                advance(30)
                tap("escape")
                assert game.flow.current == S.PAUSED
                game.execute(UICommand(C.MAIN_MENU))
                assert game.flow.current == S.MAIN_MENU
            assert len(game._save.list()) == 3
            assert not game.front.screen.buttons[0].enabled
            assert game.execute(UICommand(C.NEW_GAME))
            tap("enter")
            assert game.flow.current == S.SLOT_SELECT
            capture("slot-select.png")
            tap("arrow_down")
            tap("enter")
            assert game.flow.current == S.PLAYING and game.active_slot == 2 and game.character_name == "Vera"
            game.progression.souls = 321
            game._bus.publish(SaveRequestedEvent(1, "qa_active_slot"))
            game._flush_save()
            assert game._save.load(2).player.souls == 0  # adiado durante gameplay

            game.open_menu("map")
            advance()
            assert game._save.load(2).player.souls == 321 and game._save.load(1).player.souls == 0
            capture("map-patio.png")
            game._transform.position = Vec3(1, 22, 1)
            game._player.body.teleport(game._transform.position)
            game._previous = Transform(game._transform.position)
            game._bus.publish(AreaEnteredEvent("forge_arena"))
            advance()
            assert "menu.map.region.forge_arena" in game.ui_backend.nodes
            capture("map-forge.png")
            game.execute(UICommand(C.OPEN_OPTIONS))
            assert game.flow.current == S.OPTIONS
            screen = game.front.screen
            screen.change(0, 1)
            assert game.settings.options.config.width == 1600
            screen.select_category(3)
            screen.confirm()
            assert game.localizer.language == "en_US"
            assert game.ui_backend.labels["front.title"].get_text() == "OPTIONS"
            capture("options-language.png")
            screen.select_category(2)
            rows = game.queries.option_rows("controls")
            index = next(i for i, row in enumerate(rows) if row.id == "reset_arena")
            screen.page = index // 8
            screen.render(focus=index % 8)
            screen.confirm()
            game.keyboard("f4", True)
            advance()
            game.keyboard("f4", False)
            advance()
            persisted = SettingsStore(options_path, Config()).options
            assert persisted.language == "en_US" and persisted.config.width == 1600
            assert persisted.config.bindings[next(action for action in persisted.config.bindings if action.value == "reset_arena")] == "f4"
            capture("options-controls.png")
            tap("escape")
            assert game.flow.current == S.PAUSED
            tap("escape")
            tap("escape")
            assert game.flow.current == S.PLAYING
            tap("f4")
            assert game._transform.position.y < 0 and game.progression.souls == 321
            game.open_menu()
            game.execute(UICommand(C.MAIN_MENU))
            for _ in range(2):
                tap("arrow_down")
            tap("enter")
            assert game.flow.current == S.CREDITS
            capture("credits.png")
            tap("escape")
            assert game.flow.current == S.MAIN_MENU
            timings = []
            for _ in range(25):
                start = time.perf_counter()
                heads = game._save.list()
                timings.append((time.perf_counter() - start) * 1000)
            assert statistics.median(timings) < 5
            game.request_quit()
            assert game.flow.current == S.QUIT
            report = {"result": "ok", "slots": [dict(slot=row.slot, name=row.name, level=row.level,
                playtime_sec=round(row.playtime_sec, 3), area=row.area_id) for row in heads],
                "head_read_median_ms": round(statistics.median(timings), 4),
                "head_read_max_ms": round(max(timings), 4), "language_persisted": persisted.language,
                "rebind_persisted": "reset_arena=f4", "active_slot_autosave_verified": True,
                "physical_gamepads_detected": len(app.devices.get_devices(InputDevice.DeviceClass.gamepad)),
                "quit_without_crash": True}
            (output / "frontend.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(report, indent=2))
    finally:
        app.destroy()


if __name__ == "__main__":
    main()
