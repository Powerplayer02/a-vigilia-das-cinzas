"""Percurso nativo da 5.3, checkpoints, streaming, chefe e save reaberto."""

import argparse
from contextlib import ExitStack
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from panda3d.core import Filename
from vigilia.core.config import Config
from vigilia.core.mathx import Vec3, Transform
from vigilia.core.types import Action, AppState, InputEdge
from vigilia.core.views import UICommand, UICommandKind as C
from vigilia.combat.events import EntityDied, HPChangedEvent, DamageDealt
from vigilia.core.events import BossDefeatedEvent
from vigilia.combat.fighter import Fighter
from vigilia.engine.app import ArenaApp
from vigilia.entities.components import BodyRef
from vigilia.game import Game
from vigilia.model.stats import StatsBlock
from vigilia.save.service import SaveService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/5.3/campaign")
    out = parser.parse_args().output
    out.mkdir(parents=True, exist_ok=True)
    app = ArenaApp(Config(vsync=False), window_type="offscreen")
    try:
        with tempfile.TemporaryDirectory(prefix="vigilia-campaign-qa-") as directory, ExitStack() as cleanup:
            base = Path(directory)
            game = Game(app, Config(vsync=False), ROOT / "assets", front_end=True,
                save_path=base / "campaign.sqlite3", enemy_count=3)
            cleanup.callback(game.close)
            app.start(game)
            app.taskMgr.remove("vigilia-update")
            def frames(count=1):
                for _ in range(count):
                    game.frame(1 / 60, (0, 0), (0, 0))
            def teleport(point):
                game._player.body.teleport(point)
                game._transform.position = point
                game._previous = Transform(point)
            def interact(point):
                teleport(point)
                assert game._progression_command(InputEdge(Action.INTERACT, True))
                frames()
            def capture(name):
                frames(20)
                for _ in range(2):
                    app.graphicsEngine.render_frame()
                assert app.win.save_screenshot(Filename.from_os_specific(str(out / (name + ".png"))))
            game.execute(UICommand(C.NEW_GAME))
            game.execute(UICommand(C.SELECT_NEW_SLOT, "1"))
            screen = game.front.screen
            screen.select_class(3)
            for _ in range(10):
                screen.adjust("intelligence", 1)
            screen.create()
            assert game.flow.current == AppState.PLAYING
            current = game.build_snapshot()
            legacy = replace(current, world=replace(current.world, actors=tuple(
                actor for actor in current.world.actors if not actor.key.startswith("patio.enemy."))))
            game._world.get(game._actors["patio.enemy.0"], Fighter).hp = 0
            game.apply_snapshot(legacy)
            assert game._world.get(game._actors["patio.enemy.0"], Fighter).hp > 0
            # Pré-condição explícita: o primeiro chefe tem seu próprio aceite nativo.
            game.boss.defeated, game.boss.fighter.hp = True, 0
            game.world_state.defeated_bosses.add(game.boss.profile.id)
            game._sync_world_geometry()
            patio_key = "patio.enemy.0"
            game._world.get(game._actors[patio_key], Fighter).hp = 0
            game._bus.publish(EntityDied(game._actors[patio_key].id))
            frames()
            interact(Vec3(9, -9, 1.02))
            assert game.active_area == "catedral_submersa" and game.boss is None
            assert len(game._enemies) == 6
            assert game._audio.track_id == "cathedral_ambient"
            assert len(game._physics._characters) == 7
            capture("cathedral-entry")
            teleport(Vec3(60, 1, 1.02))
            capture("cathedral-nave")
            interact(Vec3(60, -13.2, 1.02))
            assert game.active_area == "patio_da_vigilia"
            assert game._world.get(game._actors[patio_key], Fighter).hp == 0
            interact(Vec3(9, -9, 1.02))
            game._bonfires.rest(Vec3(60, -10, 1.02))
            assert game.world_state.last_bonfire == "catedral_nave"
            dead_key, dead_entity = next((key, entity) for key, entity in game._actors.items() if key != "player")
            game._world.get(dead_entity, Fighter).hp = 0
            game._bus.publish(EntityDied(dead_entity.id))
            frames()
            assert dead_key in game.world_state.dead_common
            interact(Vec3(50, 17, 1.02))
            assert game.active_area == "patio_da_vigilia" and "cathedral_return" in game.world_state.opened_shortcuts
            assert game._world.get(game._actors[patio_key], Fighter).hp > 0  # Descanso da Catedral também o respawna.
            interact(Vec3(-9, 7, 1.02))
            assert game.active_area == "catedral_submersa"
            assert game._world.get(game._actors[dead_key], Fighter).hp == 0
            assert not game._world.get(game._actors[dead_key], BodyRef).body.active
            capture("cathedral-shortcut")
            interact(Vec3(60, 18, 1.02))
            assert game.active_area == "pantano_das_cinzas" and game.boss.profile.id == "abbess_of_the_tide"
            assert game._audio.track_id == "marsh_ambient"
            game._bonfires.rest(Vec3(120, -10, 1.02))
            assert game.world_state.last_bonfire == "pantano_margem"
            capture("marsh-shore")
            teleport(Vec3(120, 4, 1.02))
            capture("marsh-boardwalk")
            teleport(Vec3(120, -10, 1.02))
            game.open_menu("map")
            capture("discovered-map")
            assert "menu.map.region.catedral_submersa" in game.ui_backend.nodes
            assert "menu.map.region.pantano_das_cinzas" in game.ui_backend.nodes
            game.execute(UICommand(C.RESUME))
            interact(Vec3(120, 14.3, 1.02))
            assert game.boss.active and game.fog.in_fight
            assert game._audio.track_id == "tide_boss_phase1"
            capture("abbess-intro")
            frames(game.boss.profile.intro_steps)
            teleport(Vec3(120, 23, 1.02))
            old = game.boss.fighter.hp
            game.boss.fighter.hp = game.boss.profile.max_hp * .55 - 1
            game._bus.publish(HPChangedEvent(game.boss.entity.id, old, game.boss.fighter.hp, game.boss.profile.max_hp, "player"))
            assert game.boss.phase == 2 and game._audio.track_id == "tide_boss_phase2"
            capture("abbess-phase2")
            frames(game.boss.profile.transition_steps)
            midfight = game.build_snapshot()
            game._save.save(1, midfight)
            game.change_area("catedral_submersa", Vec3(60, -10, 1.02))
            assert game.load_game() and game.build_snapshot() == midfight
            assert game.boss.phase == 2 and game.boss.active and game.fog.in_fight
            # O acerto final usa a conjuração do jogador e os volumes Bullet reais.
            game._fighter.stats = StatsBlock(vigor=1000, endurance=20, intelligence=30)
            game._fighter.restore()
            game.boss.fighter.hp = 20
            teleport(Vec3(120, 23, 1.02))
            game._target = game.boss.entity
            damage = []
            game._bus.subscribe(DamageDealt, damage.append)
            for _ in range(6):
                game.keyboard("e", True)
                frames()
                game.keyboard("e", False)
                frames(120)
                if not game.boss.fighter.alive:
                    break
            assert any(event.target == game.boss.entity.id for event in damage)
            frames(game.boss.profile.death_steps)
            assert game.boss.defeated and not game.fog.blocked
            assert game.inventory.items["tide_signet"] == 1
            reward_souls = game.progression.souls
            capture("abbess-victory")
            game._bus.publish(BossDefeatedEvent(game.boss.profile.id, game.boss.profile.souls))
            assert game.progression.souls == reward_souls and game.inventory.items["tide_signet"] == 1
            game._bonfires.rest(Vec3(120, -10, 1.02))
            game._flush_save()
            assert game.boss.defeated and game.progression.souls == reward_souls
            expected = game.build_snapshot()
            assert SaveService(base / "campaign.sqlite3").load(1) == expected
            game.change_area("catedral_submersa", Vec3(60, -10, 1.02))
            assert game.load_game() and game.active_area == "pantano_das_cinzas"
            assert game.build_snapshot() == expected
            game.execute(UICommand(C.MAIN_MENU))
            game.execute(UICommand(C.CONTINUE))
            game.execute(UICommand(C.LOAD_SLOT, "1"))
            assert game.boss.defeated and game.active_area == "pantano_das_cinzas"
            assert game.inventory.items["tide_signet"] == 1
            resource_counts = []
            for _ in range(4):
                game.change_area("catedral_submersa", Vec3(60, -10, 1.02))
                frames()
                resource_counts.append((len(game._physics._characters), len(game._contacts._nodes), len(game._renderer._combat_gear),
                    sum(len(h) for h in game._bus._handlers.values())))
                game.change_area("pantano_das_cinzas", Vec3(120, -10, 1.02))
                frames()
            assert len(set(resource_counts)) == 1, resource_counts
            game.change_area("catedral_submersa", Vec3(60, -10, 1.02))
            death_position = game._transform.position
            carried = game.progression.souls
            game._fighter.hp = 0
            game._bus.publish(EntityDied(game._entity.id))
            frames(121)
            assert game.active_area == "pantano_das_cinzas"
            assert game.progression.bloodstain.position == death_position
            assert game.progression.bloodstain.souls == carried
            game.change_area("catedral_submersa", death_position)
            interact(death_position)
            assert game.progression.souls == carried and game.progression.bloodstain is None
            game.hud.accessibility(1.4, True)
            capture("separate-spell-item-hud")
            assert "Estilhaço" in game.ui_backend.labels["hud.spell.label"].get_text()
            assert "ITEM" in game.ui_backend.labels["hud.quick"].get_text()
            report = dict(result="ok", source_boss_precondition="Warden flag seeded; Warden covered by separate native regression",
                regions=["catedral_submersa", "pantano_das_cinzas"], new_enemy_profiles=3, return_shortcut_persisted=True,
                unloaded_enemy_death_restored=True, two_phase_boss=True, own_music=True, real_bullet_spell_kill=True,
                patio_common_death_persisted=True,
                legacy_missing_patio_agents_initialized=True,
                unique_drop="tide_signet", duplicate_reward_prevented=True, save_reopened=True,
                load_switches_region=True, cross_region_death_respawn_and_bloodstain_recovery=True,
                midfight_phase2_restored=True,
                no_growth_in_repeated_streaming=True, cathedral_counts=resource_counts, separate_spell_item_hud=True)
            (out / "campaign.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(report, ensure_ascii=False))
    finally:
        app.destroy()


if __name__ == "__main__":
    main()
