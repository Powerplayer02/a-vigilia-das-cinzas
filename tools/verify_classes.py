"""Cria as cinco classes na UI nativa e reabre cada save em um processo limpo."""

import argparse
from contextlib import ExitStack
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from panda3d.core import Filename
from vigilia.core.config import Config
from vigilia.core.mathx import Vec3, Transform
from vigilia.core.types import AppState
from vigilia.core.views import UICommand, UICommandKind as C
from vigilia.combat.fighter import Fighter
from vigilia.engine.app import ArenaApp
from vigilia.game import Game
from vigilia.model.classes import CHARACTER_CLASSES
from vigilia.save.service import SaveService
from vigilia.save.serializers import encode

ALLOCATIONS = {
    "warrior": {"strength": 4, "endurance": 3, "vigor": 3},
    "knight": {"vigor": 5, "endurance": 5},
    "assassin": {"dexterity": 7, "luck": 3},
    "mage": {"intelligence": 7, "vigor": 3},
    "cleric": {"faith": 7, "vigor": 3},
}

REOPEN = """
import hashlib, json, sys
from pathlib import Path
sys.path.insert(0, 'src')
from vigilia.save.service import SaveService
from vigilia.save.serializers import encode
from vigilia.model.bosses import load_boss_profile
load_boss_profile(Path('data/bosses/warden.toml'))
snapshot = SaveService(Path(sys.argv[1])).load(int(sys.argv[2]))
assert snapshot.player.character_class == sys.argv[3]
assert hashlib.sha256(''.join(encode(snapshot)).encode()).hexdigest() == sys.argv[4]
assert not any(key.split('.')[0] in ('panda3d', 'direct', 'pygame', 'numpy') for key in sys.modules)
print(json.dumps({'reopened': True, 'domain_without_native_imports': True}))
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/5.1")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    config = Config(vsync=False)
    app = ArenaApp(config, window_type="offscreen")
    try:
        with tempfile.TemporaryDirectory(prefix="vigilia-class-qa-") as directory, ExitStack() as cleanup:
            base = Path(directory)
            game = Game(app, config, ROOT / "assets", save_path=base / "initial.sqlite3",
                        front_end=True, enemy_count=0)
            cleanup.callback(game.close)
            app.start(game)
            app.taskMgr.remove("vigilia-update")

            def advance(count=1):
                for _ in range(count):
                    game.frame(1 / 60, (0, 0), (0, 0))

            def capture(name):
                for _ in range(2):
                    app.graphicsEngine.render_frame()
                assert app.win.save_screenshot(Filename.from_os_specific(str(args.output / name)))

            def tap(key):
                game.keyboard(key, True)
                advance()
                game.keyboard(key, False)
                advance()

            results = []
            for index, (identity, profile) in enumerate(CHARACTER_CLASSES.items()):
                if game.flow.current != AppState.MAIN_MENU:
                    game.execute(UICommand(C.MAIN_MENU))
                database = base / f"{identity}.sqlite3"
                game._save = SaveService(database)
                game._has_session = False
                slot = index % 3 + 1
                game.execute(UICommand(C.NEW_GAME))
                game.execute(UICommand(C.SELECT_NEW_SLOT, str(slot)))
                screen = game.front.screen
                screen.select_class(index)
                game.ui_backend.text("front.name", "Vésper " + identity)
                for stat, points in ALLOCATIONS[identity].items():
                    for _ in range(points):
                        screen.adjust(stat, 1)
                assert screen.remaining == 0
                advance()
                capture(identity + "-creation.png")
                slot = index % 3 + 1
                screen.select_slot(slot)
                screen.create()
                assert game.flow.current == AppState.PLAYING
                game._practice_wait = 10000
                assert game.inventory.equipped_weapon == profile.starting_weapon
                assert game.inventory.spells == profile.starting_spells
                assert game.starting_allocation == ALLOCATIONS[identity]
                advance(12)

                # Todas as armas iniciam o moveset completo sem erro de catálogo.
                tap("mouse1")
                assert game._fighter.attack is not None
                melee_kind = game._fighter.attack.definition.kind.value
                advance(90)

                spell_result = None
                if identity == "mage":
                    target = game._practice_target
                    target_pose = game._world.get(target, Transform)
                    point = target_pose.position + Vec3(0, -3.5, 0)
                    game._player.body.teleport(point)
                    game._transform.position = point
                    game._previous = Transform(point)
                    game._target = target
                    game._camera.set_target(target_pose.position)
                    advance(2)
                    defender = game._world.get(target, Fighter)
                    old_hp = defender.hp
                    tap("e")
                    advance(23)
                    assert defender.hp < old_hp, "O projétil deve acertar os volumes Bullet reais"
                    spell_result = {"kind": "arcane_bolt", "damage": round(old_hp - defender.hp, 3)}
                elif identity == "cleric":
                    game._fighter.hp -= 80
                    old_hp = game._fighter.hp
                    tap("e")
                    advance(31)
                    assert game._fighter.hp == game._fighter.max_hp
                    spell_result = {"kind": "mending_light", "healed": game._fighter.hp - old_hp}
                game._draw_combat()
                capture(identity + "-gameplay.png")

                snapshot = game.build_snapshot()
                game._save.save(slot, snapshot)
                checksum = hashlib.sha256("".join(encode(snapshot)).encode()).hexdigest()
                check = subprocess.run([sys.executable, "-c", REOPEN, str(database), str(slot), identity, checksum],
                    cwd=ROOT, capture_output=True, text=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if check.returncode:
                    raise RuntimeError(check.stderr)
                reopened = json.loads(check.stdout)
                game.apply_snapshot(SaveService(database).load(slot))
                assert game._fighter.stats == snapshot.player.fighter.stats
                assert game.starting_allocation == ALLOCATIONS[identity]
                results.append({"class": identity, "slot": slot, "weapon": profile.starting_weapon,
                    "stats": asdict(game._fighter.stats), "allocation": game.starting_allocation.copy(),
                    "gear": list(game.inventory.equipped_gear), "spells": list(game.inventory.spells),
                    "melee_started": melee_kind, "spell_result": spell_result, **reopened})

            # A apresentação da criação também precisa ser legível em inglês.
            game.execute(UICommand(C.MAIN_MENU))
            game.localizer.set_language("en_US")
            game.execute(UICommand(C.NEW_GAME))
            empty = next(row.slot for row in game._save.list_slots() if not row.occupied)
            game.execute(UICommand(C.SELECT_NEW_SLOT, str(empty)))
            game.front.screen.select_class(3)
            advance()
            capture("mage-creation-en.png")
            report = {"result": "ok", "classes": results,
                "native_bullet_spell_hit": True, "native_healing": True,
                "fresh_process_save_load": True, "legacy_saves_migrated_by_tests": True}
            (args.output / "classes.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        app.destroy()


if __name__ == "__main__":
    main()
