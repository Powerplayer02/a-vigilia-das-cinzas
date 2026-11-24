"""Smoke do main real, com saída agendada e banco/preferências temporários."""

import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from vigilia.engine.app import ArenaApp
from vigilia.game import Game
import main as launcher


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-diagnostics", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = dict(no_diagnostics=args.no_diagnostics, enable_calls=0)
    original_enable, original_run = Game.enable_diagnostics, ArenaApp.run
    def enable(game, *values, **options):
        result["enable_calls"] += 1
        return original_enable(game, *values, **options)
    def run(app):
        result["diagnostics_attached"] = getattr(app, "diagnostics", None) is not None
        result["renderer"] = app.win.get_gsg().get_driver_renderer()
        def finish(task):
            app.userExit()
            return task.done
        app.taskMgr.do_method_later(1.2, finish, "launcher-qa-exit", sort=55)
        original_run(app)
        if getattr(app, "diagnostics", None):
            app.diagnostics.close()
            result["quarantined"] = app.diagnostics.quarantined
    Game.enable_diagnostics, ArenaApp.run = enable, run
    with tempfile.TemporaryDirectory(prefix="vigilia-launcher-qa-") as temp:
        sys.argv = ["main.py", "--save-file", str(Path(temp)/"save.sqlite3"),
            "--options-file", str(Path(temp)/"options.toml"), "--diagnostics-dir", str(args.output.parent / "launcher-spikes")]
        if args.no_diagnostics:
            sys.argv.append("--no-diagnostics")
        launcher.main()
    assert result["enable_calls"] == int(not args.no_diagnostics)
    assert result["diagnostics_attached"] == (not args.no_diagnostics)
    assert not result.get("quarantined", False)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
