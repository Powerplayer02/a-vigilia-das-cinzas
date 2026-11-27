"""Percorre a UI real com Panda3D, pausa de mundo, comandos e save SQLite."""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from panda3d.core import Filename, InputDevice
from vigilia.combat.attack import AttackKind
from vigilia.combat.events import EntityDied
from vigilia.combat.fighter import Fighter
from vigilia.combat.status import StatusEffect
from vigilia.core.config import Config
from vigilia.core.types import GameState
from vigilia.core.views import UICommand, UICommandKind
from vigilia.engine.app import ArenaApp
from vigilia.engine.input import InputMode
from vigilia.game import Game


def main():
    output = ROOT / "artifacts/4.5.1/ui-qa"
    output.mkdir(parents=True, exist_ok=True)
    config = Config(vsync=False)
    app = ArenaApp(config, window_type="offscreen")
    try:
        with tempfile.TemporaryDirectory(prefix="vigilia-ui-qa-") as temp:
            game = Game(app, config, ROOT / "assets", save_path=Path(temp) / "qa.sqlite3", enemy_count=3)
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
                for _ in range(2):
                    app.graphicsEngine.renderFrame()
                assert app.win.save_screenshot(Filename.from_os_specific(str(output / name)))

            game.progression.souls = 500
            game._fighter.status.active[StatusEffect.POISON] = 1800
            game._fighter.status.buildup[StatusEffect.BLEED] = 42
            advance(5)
            assert "[V] 1×" in game.hud.statuses.value
            capture("hud.png")
            tap("escape")
            frozen, ai_steps = game.build_snapshot(), game.ai.step
            advance(180)
            assert game.build_snapshot() == frozen and game.ai.step == ai_steps
            assert game.input.mode == InputMode.MENU
            capture("pause.png")

            # Inventário por foco: segunda opção, arma da direita, confirmar.
            tap("arrow_down")
            tap("enter")
            assert game.menus.page == "inventory"
            tap("arrow_right")
            tap("enter")
            assert game.inventory.equipped_weapon == "axe" and game._fighter.weapon.spec_id == "axe"
            assert game._save.load().player.equipped_weapon == "axe"
            capture("inventory.png")
            tap("tab")
            assert len(game.menus.content.items) == 2

            # Subir de nível ainda durante a pausa deve salvar sem tick de física.
            tap("escape")
            for _ in range(3):
                tap("arrow_down")
            tap("enter")
            assert game.menus.page == "level"
            hp_before = game._fighter.hp
            tap("2")
            assert game._fighter.stats.vigor == 11 and game._fighter.max_hp == 146
            assert game._fighter.hp == hp_before + 6 and game.progression.souls == 412
            saved = game._save.load()
            assert saved.player.fighter.stats.vigor == 11 and saved.player.souls == 412
            assert "146" in game.hud.hp_text.value and game.ai.step == ai_steps
            capture("level-up.png")
            tap("escape")
            tap("enter")
            assert game.menus.page == "status"
            capture("status.png")

            # Um clique e movimento segurados no menu não iniciam ação ao voltar.
            game.keyboard("mouse1", True)
            game.keyboard("w", True)
            tap("escape")
            tap("escape")
            assert game._app.state == GameState.PLAYING
            advance(3)
            assert game._fighter.attack is None and not game.input.held().actions
            game.keyboard("mouse1", False)
            game.keyboard("w", False)
            tap("mouse1")
            advance(2)
            assert game._fighter.attack is not None
            assert game._fighter.attack.definition.windup == 15  # Primeiro golpe do machado.
            assert game._fighter.stamina < game._fighter.stats.max_stamina

            # Dano, recompensa e expiração são observados pelo mesmo adaptador do HUD.
            game._fighter.hp = 70
            dummy = game._actors["dummy_0"]
            game._world.get(dummy, Fighter).hp = 0
            game._bus.publish(EntityDied(dummy.id))
            game._fighter.status.active = {StatusEffect.POISON: 1}
            game._fighter.status.buildup.clear()
            advance(2)
            assert "500" in game.hud.souls.value and not game.hud.statuses.value
            assert "70 / 146" in game.hud.hp_text.value
            capture("hud-combat.png")
            print(json.dumps({"result": "ok", "paused_frames": 180, "simulation_steps_during_pause": 0,
                "level": game.progression.level, "souls": game.progression.souls,
                "weapon": game._fighter.weapon.spec_id, "autosave_verified": True,
                "next_attack_uses_equipped_moveset": True,
                "physical_gamepads_detected": len(app.devices.get_devices(InputDevice.DeviceClass.gamepad)),
                "screenshots": 6}, indent=2))
            # Release Windows slot locks before TemporaryDirectory removes its files.
            game._save.close()
    finally:
        app.destroy()


if __name__ == "__main__":
    main()
