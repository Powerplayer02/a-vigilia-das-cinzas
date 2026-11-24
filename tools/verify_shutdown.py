"""Conta COMMITs no fechamento nativo; verifica preto apresentado no checkpoint."""

import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from panda3d.core import PNMImage
from vigilia.core.config import Config
from vigilia.core.events import SaveRequestedEvent
from vigilia.core.mathx import Vec3
from vigilia.engine.app import ArenaApp
from vigilia.game import Game


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wait-for-native-close", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/5.5/shutdown.json")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    phase, commits, covers = "setup", [], []
    original_connect = sqlite3.connect
    def connect(*values, **options):
        connection = original_connect(*values, **options)
        def trace(statement):
            if statement.strip().upper() == "COMMIT":
                commits.append(dict(phase=phase, time=time.perf_counter()))
        connection.set_trace_callback(trace)
        return connection
    sqlite3.connect = connect
    app = ArenaApp(Config(vsync=False))
    try:
        with tempfile.TemporaryDirectory(prefix="vigilia-shutdown-") as temporary, ExitStack() as cleanup:
            game = Game(app, Config(vsync=False), ROOT / "assets", save_path=Path(temporary)/"save.sqlite3",
                settings_path=Path(temporary)/"options.toml", enemy_count=0)
            cleanup.callback(game.close)
            app.start(game)
            app.taskMgr.remove("vigilia-update")
            save = game._save.save
            def covered_save(*values, **options):
                pixels = PNMImage()
                assert app.win.get_screenshot(pixels)
                rgb = tuple(pixels.get_xel(pixels.get_x_size()//2, pixels.get_y_size()//2))
                assert max(rgb) < .01, rgb
                covers.append(dict(phase=phase, presented_center_rgb=rgb))
                return save(*values, **options)
            game._save.save = covered_save
            phase = "checkpoint"
            game._bonfires.rest(Vec3(0,-6.5,1.02))
            game.frame(1/60, (0,0), (0,0))
            before = game._save.load(1)
            assert before is not None and covers
            with game._save.repository.database.connect() as connection:
                synchronous = connection.execute("PRAGMA synchronous").fetchone()[0]
                journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
            assert synchronous == 1  # NORMAL; 334ms não prova FULL.
            game.progression.souls += 17
            game._bus.publish(SaveRequestedEvent(1, "enemy_death"))
            phase = "normal_window_close"
            def close_window(task):
                app.userExit()
                return task.done
            if not args.wait_for_native_close:
                app.taskMgr.do_method_later(.1, close_window, "qa-native-window-close")
            else:
                print("READY_FOR_NATIVE_ALT_F4", flush=True)
            app.run()
            phase = "destroy"
            app.destroy()
            assert not [row for row in commits if row["phase"] in ("normal_window_close", "destroy")]
            phase = "verification"
            after = game._save.load(1)
            assert after == before
            result = dict(native_close="OS Alt+F4 -> window event -> userExit -> request_quit" if args.wait_for_native_close else "programmatic userExit -> request_quit (not an OS close test)",
                commits=commits, shutdown_commits=0, checkpoint_presented_before_commit=covers,
                checkpoint_preserved=True, dirty_shutdown_state_not_saved=True,
                synchronous=synchronous, synchronous_name="NORMAL", journal_mode=journal_mode)
            args.output.write_text(json.dumps(result, indent=2), encoding="utf8")
            print(json.dumps(dict(shutdown_commits=0, synchronous=synchronous, checkpoint_masked=True)))
    finally:
        app.destroy()
        sqlite3.connect = original_connect


if __name__ == "__main__":
    main()
