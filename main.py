"""Ponto de entrada da Vigília das Cinzas."""

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def main() -> None:
    """Inicia a arena com a configuração selecionada."""
    parser = argparse.ArgumentParser(description="A Vigília das Cinzas")
    parser.add_argument("--config", type=Path, default=ROOT / "data" / "config.toml")
    parser.add_argument("--save-file", type=Path, default=ROOT / "saves" / "slot1.sqlite3")
    parser.add_argument("--enemies", type=int, default=3, choices=range(21))
    parser.add_argument("--options-file", type=Path)
    parser.add_argument("--no-diagnostics", action="store_true", help="Desliga o flight recorder de QA para release/medição de FPS")
    parser.add_argument("--diagnostics-dir", type=Path, default=ROOT / "artifacts/spikes")
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT / "src"))
    from vigilia.core.config import load_config
    from vigilia.engine.app import ArenaApp
    from vigilia.engine.prewarm import prewarm_scene
    from vigilia.game import Game
    from vigilia.core.settings import SettingsStore

    try:
        defaults = load_config(args.config)
        options_path = args.options_file or ROOT / "data/settings.toml"
        config = SettingsStore(options_path, defaults, legacy_path=args.save_file.with_name("options.json")).options.config
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    app = ArenaApp(config)
    try:
        game = Game(app, defaults, ROOT / "assets", save_path=args.save_file, enemy_count=args.enemies,
                    front_end=True, settings_path=options_path)
        app.start(game)
        prewarm_scene(app)
        if not args.no_diagnostics:
            game.enable_diagnostics(args.diagnostics_dir)
        app.run()
    finally:
        app.destroy()


if __name__ == "__main__":
    main()
