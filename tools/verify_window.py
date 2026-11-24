"""Smoke test de janela real, alteração de resolução e encerramento pelo fluxo."""

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from panda3d.core import Filename
from vigilia.core.config import Config
from vigilia.core.types import AppState
from vigilia.core.views import UICommand, UICommandKind
from vigilia.engine.app import ArenaApp
from vigilia.game import Game


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/4.5.2")
    output = parser.parse_args().output
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vigilia-window-qa-") as temporary:
        config = Config(vsync=False)
        app = ArenaApp(config)
        try:
            game = Game(app, config, ROOT / "assets", front_end=True, enemy_count=0,
                        save_path=Path(temporary) / "qa.sqlite3")
            app.start(game)
            for _ in range(12):
                app.taskMgr.step()
            assert game.flow.current == AppState.MAIN_MENU
            game.execute(UICommand(UICommandKind.OPEN_OPTIONS))
            game.front.screen.change(0, 1)
            for _ in range(20):
                app.taskMgr.step()
            size = [app.win.get_x_size(), app.win.get_y_size()]
            assert size == [1600, 900]
            assert app.win.save_screenshot(Filename.from_os_specific(str(output / "window-options.png")))
            game.front.screen.change(1, 1)
            for _ in range(20):
                app.taskMgr.step()
            assert app.win.get_properties().get_fullscreen()
            fullscreen = [app.win.get_x_size(), app.win.get_y_size()]
            game.front.screen.change(1, 1)
            for _ in range(20):
                app.taskMgr.step()
            assert not app.win.get_properties().get_fullscreen()
            assert [app.win.get_x_size(), app.win.get_y_size()] == size
            game.request_quit()
            assert game.flow.current == AppState.QUIT
            report = dict(result="ok", native_resolution=size, fullscreen_roundtrip=True, fullscreen_resolution=fullscreen, quit_without_crash=True)
            (output / "window.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps(report))
        finally:
            app.destroy()


if __name__ == "__main__":
    main()
