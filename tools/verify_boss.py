"""Verificação integrada da 4.4 com Bullet, render offscreen e save temporário."""

import argparse
from contextlib import ExitStack
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from panda3d.core import Filename
from vigilia.combat.attack import Attack, AttackKind
from vigilia.combat.events import EntityDied, HPChangedEvent
from vigilia.core.config import Config
from vigilia.core.mathx import Transform, Vec3
from vigilia.core.types import Action, InputEdge
from vigilia.engine.app import ArenaApp
from vigilia.game import Game
from vigilia.model.progression import Bloodstain
from vigilia.model.stats import StatsBlock
from vigilia.world.bonfire import BONFIRES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/4.4")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    config = Config(vsync=False)
    app = ArenaApp(config, window_type="offscreen")
    try:
        with tempfile.TemporaryDirectory(prefix="vigilia-boss-qa-") as temporary, ExitStack() as cleanup:
            game = Game(app, config, ROOT / "assets", save_path=Path(temporary) / "qa.sqlite3", enemy_count=0)
            cleanup.callback(game.close)
            app.start(game)
            app.taskMgr.remove("vigilia-update")
            boss = game.boss
            assert boss is not None

            def advance(count):
                for _ in range(count):
                    game.frame(1 / 60, (0, 0), (0, 0))

            def teleport(point):
                game._player.body.teleport(point)
                game._transform.position = point
                game._previous = Transform(point)

            def capture(name):
                game._draw_combat()
                for _ in range(2):
                    app.graphicsEngine.renderFrame()
                assert app.win.save_screenshot(Filename.from_os_specific(str(args.output / name)))

            # Atalho e névoa percorrem o mesmo despacho de comando usado por F.
            teleport(Vec3(0, 7.3, 1))
            game._progression_command(InputEdge(Action.INTERACT, True))
            assert game.shortcut.opened and not game.shortcut.collider.active
            teleport(Vec3(0, 11.8, 1))
            game._progression_command(InputEdge(Action.INTERACT, True))
            assert boss.active and boss.intro_remaining == 180
            assert game.music_track == "boss_phase1"
            advance(1)
            capture("intro.png")
            advance(180)
            assert not boss.fighter.invulnerable

            # Fase e barra são dirigidas pelos eventos reais do combate.
            boss.fighter.hp = 1500
            game._bus.publish(HPChangedEvent(boss.entity.id, 3200, 1500, 3200, "player"))
            advance(1)
            capture("phase2.png")
            assert game.world_state.boss_phases[boss.profile.id] == 2
            assert game.music_track == "boss_phase2"
            game._save.save(1, game.build_snapshot())
            assert game.load_game()
            assert boss.fighter.hp == 1500 and boss.phase == 2
            advance(91)

            # Confere ring visível e o raio final com a hitbox Bullet ativa.
            pose = game._world.get(boss.entity, Transform)
            teleport(pose.position + Vec3(0, -7.2, -.65))
            game._fighter.stats = StatsBlock(vigor=1000)
            game._fighter.restore()
            boss.fighter.attack = Attack(boss.profile.weapon.attack(AttackKind.FIRE_AOE_RING), 88)
            game._target = boss.entity
            game._camera.set_target(pose.position)
            game._camera.update(game._transform.position, 1)
            game._evaluate_poses()
            game._sync.sync({entity: pose.volumes for entity, pose in game._poses.items()})
            game.frame(0, (0, 0), (0, 0))
            capture("fire-ring.png")
            assert boss.visual_radius > 5.8

            # Descanso e teleporte preservam almas/mancha com o chefe vivo.
            game.progression.souls = 500
            game.progression.bloodstain = Bloodstain(Vec3(2, 3, 1), 120)
            teleport(BONFIRES["patio_sul"].position)
            game._bonfires.rest(game._transform.position)
            game._flush_save()
            assert game.load_game()
            assert game.progression.souls == 500 and game.progression.bloodstain.souls == 120
            assert boss.fighter.hp == 3200 and boss.phase == 1 and not boss.active
            game._bonfires.rest(BONFIRES["patio_norte"].position)
            game._bonfires.travel(game._transform.position)
            game._flush_save()
            assert game.load_game() and game.progression.souls == 500

            # Vitória espera 240 passos, remove a névoa e credita uma recompensa.
            boss.start()
            boss.fighter.hp = 0
            game._bus.publish(EntityDied(boss.entity.id))
            advance(239)
            assert boss.profile.id not in game.world_state.defeated_bosses
            advance(1)
            assert boss.profile.id in game.world_state.defeated_bosses
            assert not game.fog.collider.active
            rewarded = game.progression.souls
            advance(20)
            assert game.progression.souls == rewarded == 3140
            assert game.load_game()
            assert boss.defeated and not boss.fighter.alive
            assert game.build_snapshot().world.bosses[0].fighter is None
            report = {"result": "ok", "souls_after_reward": rewarded,
                "shortcut_persisted": game.shortcut.opened, "boss_defeated": boss.defeated,
                "fog_removed": not game.fog.collider.active, "snapshots": 3}
            (args.output / "boss.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps(report, indent=2))
    finally:
        app.destroy()


if __name__ == "__main__":
    main()
