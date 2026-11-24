"""QA nativo da 5.4 com diagnóstico ativo e precondições explicitamente semeadas."""

import argparse
from contextlib import ExitStack
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from panda3d.core import Filename, ClockObject, PNMImage
from vigilia.core.config import Config
from vigilia.core.mathx import Vec3, Transform
from vigilia.core.types import AppState as S
from vigilia.core.views import UICommand, UICommandKind as C
from vigilia.core.events import BossDefeatedEvent
from vigilia.combat.events import HPChangedEvent, DamageDealt
from vigilia.engine.app import ArenaApp
from vigilia.game import Game
from vigilia.model.characters import CHARACTER_CLASSES
from vigilia.model.stats import StatsBlock
from vigilia.save.service import SaveService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/5.4/native")
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    app = ArenaApp(Config(vsync=False), window_type="offscreen")
    monitor = None
    try:
        with tempfile.TemporaryDirectory(prefix="vigilia-final-qa-") as temporary, ExitStack() as cleanup:
            base = Path(temporary)
            game = Game(app, Config(vsync=False), ROOT / "assets", front_end=True,
                save_path=base / "campaign.sqlite3", settings_path=base / "options.toml", enemy_count=3)
            cleanup.callback(game.close)
            app.start(game)
            app.taskMgr.remove("vigilia-update")
            app._clock.set_mode(ClockObject.M_non_real_time)
            app._clock.set_dt(1/60)
            app.graphicsEngine.render_frame()
            app.graphicsEngine.render_frame()
            monitor = game.enable_diagnostics(out / "spikes", report_path=out / "diagnostics.json")
            pending, screenshots = [], []
            def update(task):
                for operation in pending[:]:
                    operation()
                pending.clear()
                game.frame(1/60, (0, 0), (0, 0))
                return task.cont
            app.taskMgr.add(update, "qa-game-step", sort=10)
            def frames(count=1):
                for _ in range(count):
                    app.taskMgr.step()
            def act(operation):
                pending.append(operation)
                frames()
            def tap(key):
                act(lambda: game.keyboard(key, True))
                act(lambda: game.keyboard(key, False))
            def warp(point):
                game._player.body.teleport(point)
                game._transform.position = point
                game._previous = Transform(point)
            def capture(name):
                frames(2)
                def grab():
                    image = PNMImage()
                    assert app.win.get_screenshot(image)
                    screenshots.append((name, image))
                act(grab)
            def seed_previous_victory():
                # Só os dois chefes já aceitos: não representa vitória manual neste ensaio.
                game.boss.active, game.boss.fighter.hp, game.boss.death_remaining = True, 0, 1
            def use_passage(identity):
                passage = next(p for p in game._passages() if p.id == identity)
                act(lambda: warp(passage.position))
                tap("f")
            assert game.flow.current == S.MAIN_MENU
            capture("main-menu")
            tap("enter")
            act(lambda: game.execute(UICommand(C.SELECT_NEW_SLOT, "1")))
            screen = game.front.screen
            previews = {}
            for index, identity in enumerate(CHARACTER_CLASSES):
                act(lambda index=index: screen.select_class(index))
                previews[identity] = [(stat.id, stat.value) for stat in screen.classes[index].attributes]
            mage_index = list(CHARACTER_CLASSES).index("mage")
            act(lambda: screen.select_class(mage_index))
            act(lambda: game.ui_backend.text("front.name", "Vésper QA"))
            for _ in range(10):
                act(lambda: screen.adjust("vigor", 1))
            capture("creation-five-classes")
            act(screen.create)
            assert game.flow.current == S.PLAYING and game.character_class == "mage"
            assert game._save.load(1).player.character_class == "mage"
            assert "ember_shard" in game.inventory.spells
            act(lambda: setattr(game._fighter, "stats", replace(game._fighter.stats, vigor=10000)))
            act(game._fighter.restore)
            game._practice_wait = 100000
            # Abrir o arco novo requer as duas vitórias anteriores.
            act(seed_previous_victory)
            frames(2)
            use_passage("patio-cathedral")
            assert game.active_area == "catedral_submersa"
            cathedral_to_marsh = next(p for p in game._passages() if p.target == "pantano_das_cinzas")
            use_passage(cathedral_to_marsh.id)
            assert game.active_area == "pantano_das_cinzas"
            act(seed_previous_victory)
            frames(2)
            use_passage("ruins-seal")
            assert game.active_area == "ruinas_subterraneas"
            act(lambda: game._bonfires.rest(Vec3(180,-10,1.02)))
            capture("ruins-crypt")
            use_passage("ruins_lift")
            assert game.active_area == "patio_da_vigilia" and "ruins_lift" in game.world_state.opened_shortcuts
            use_passage("patio-ruins-lift")
            act(lambda: game._bonfires.rest(Vec3(180,30,1.02)))
            use_passage("ruins_furnace")
            assert game.active_area == "forno_da_vigilia"
            act(lambda: game._bonfires.rest(Vec3(240,-10,1.02)))
            capture("furnace-threshold")
            act(lambda: warp(Vec3(240,10.5,1.02)))
            tap("f")
            frames(181)
            assert game.boss.active and game.boss.phase == 1
            capture("custodian-phase1")
            def threshold(fraction):
                old = game.boss.fighter.hp
                game.boss.fighter.hp = game.boss.profile.max_hp * fraction
                game._bus.publish(HPChangedEvent(game.boss.entity.id, old, game.boss.fighter.hp, game.boss.profile.max_hp, "player"))
            act(lambda: threshold(.65))
            frames(91)
            assert game.boss.phase == 2
            capture("custodian-phase2")
            act(lambda: threshold(.32))
            frames(91)
            assert game.boss.phase == 3 and game._audio.track_id == "cinder_boss_phase3"
            damage = []
            game._bus.subscribe(DamageDealt, damage.append)
            act(lambda: warp(game.boss.hazard_position + Vec3(0,0,1)))
            frames(90)
            assert any(event.attack_kind == "ember_vent" for event in damage)
            capture("custodian-phase3-vent")
            tap("f8")
            tap("escape")
            assert game.flow.current == S.PAUSED
            saved = game._save.load(1)
            assert saved.world.bosses[0].phase == 3
            timer = game.boss.hazard_step
            for page in ("status", "inventory", "equipment", "map"):
                act(lambda page=page: game.menus.open(page))
            map_view = game.menus.content
            capture("map-five-regions-overview")
            act(map_view.confirm)
            capture("map-five-regions-focused")
            assert game.boss.hazard_step == timer
            act(lambda: game.menus.open("options"))
            assert game.flow.current == S.OPTIONS
            act(lambda: game.execute(UICommand(C.BACK)))
            act(lambda: game.execute(UICommand(C.MAIN_MENU)))
            act(lambda: game.execute(UICommand(C.CONTINUE)))
            def restore():
                game.execute(UICommand(C.LOAD_SLOT, "1"))
                assert game.boss.phase == 3 and game.boss.hazard_step == timer
                assert game.world_state.last_bonfire == "forno_limiar" and "ruins_lift" in game.world_state.opened_shortcuts
                assert "ember_shard" in game.inventory.spells
                game.open_menu("pause")
            act(restore)
            act(lambda: game.execute(UICommand(C.RESUME)))
            assert game._audio.track_id == "cinder_boss_phase3"
            # Apenas o golpe final é real: HP/fases foram semeados para QA rápido e determinístico.
            def setup_final_blow():
                game._fighter.restore()
                game.boss.fighter.hp = 1
                game.boss.fighter.invulnerable = False
                game.boss.intro_remaining = game.boss.transition_remaining = 0
                point = game._world.get(game.boss.entity, Transform).position
                warp(point + Vec3(0,-4,0))
                game._target = game.boss.entity
            act(setup_final_blow)
            for _ in range(4):
                tap("e")
                frames(100)
                if not game.boss.fighter.alive:
                    break
            assert any(event.target == game.boss.entity.id for event in damage)
            frames(250)
            assert game.boss.defeated and "last_ember_custodian" in game.world_state.defeated_bosses
            assert game.inventory.items["ember_heart"] == 1
            souls = game.progression.souls
            act(lambda: game._bus.publish(BossDefeatedEvent(game.boss.profile.id, 6000)))
            assert game.progression.souls == souls and game.inventory.items["ember_heart"] == 1
            capture("custodian-victory")
            checkpoint = game.build_snapshot()
            endings = []
            for index, choice in enumerate(("maintain", "extinguish", "transform")):
                act(lambda: game.apply_snapshot(checkpoint))
                act(lambda: warp(Vec3(240,35,1.02)))
                tap("f")
                assert game.menus.page == "ending"
                ui = game.menus.content
                act(lambda index=index: ui.grid.select(index))
                act(ui.confirm)
                assert game.world_state.ending == ""
                act(ui.confirm)  # Cancelar recebe o foco inicial.
                assert game.world_state.ending == ""
                act(lambda index=index: ui.grid.select(index))
                act(ui.confirm)
                capture("ending-review-" + choice)
                act(lambda: ui.grid.select(1))
                act(ui.confirm)
                assert game.flow.current == S.CREDITS and game.world_state.ending == choice
                capture("epilogue-" + choice)
                if choice == "maintain":
                    act(lambda: game.execute(UICommand(C.MAIN_MENU)))
                    act(lambda: game.execute(UICommand(C.CONTINUE)))
                    act(lambda: game.execute(UICommand(C.LOAD_SLOT, "1")))
                    assert game.flow.current == S.CREDITS and not game.world_state.credits_seen
                act(lambda: game.execute(UICommand(C.BACK)))
                assert game.flow.current == S.PLAYING and game.world_state.credits_seen
                stored = game._save.load(1)
                assert stored.world.ending == choice and stored.world.credits_seen
                target = SaveService(base / (choice + ".sqlite3"))
                target.save(1, stored)
                target.close()
                endings.append(choice)
            act(lambda: game.execute(UICommand(C.MAIN_MENU)))
            act(lambda: game.execute(UICommand(C.CONTINUE)))
            act(lambda: game.execute(UICommand(C.LOAD_SLOT, "1")))
            assert game.flow.current == S.PLAYING and game.world_state.ending == "transform"
            capture("post-credits-gameplay")
            assert game._audio.track_id == "furnace_ambient"
            monitor.close()
            for name, image in screenshots:
                assert image.write(Filename.from_os_specific(str(out / (name + ".png"))))
            # Ler os três desfechos em processo limpo, fora da amostra de frame de QA.
            check = "import sys;sys.path.insert(0,sys.argv[1]);from pathlib import Path;from vigilia.save.service import SaveService; s=SaveService(Path(sys.argv[2])).load(1);assert s.world.ending==sys.argv[3] and s.world.credits_seen;assert 'panda3d.core' not in sys.modules"
            for choice in endings:
                subprocess.run([sys.executable, "-c", check, str(ROOT / "src"), str(base / (choice + ".sqlite3")), choice], check=True, capture_output=True)
            result = dict(renderer=app.win.get_gsg().get_driver_renderer(), resolution=[app.win.get_x_size(), app.win.get_y_size()],
                window_type="offscreen", simulation_dt=1/60, build_id=monitor.build_id, diagnostics=monitor.report(), class_previews=previews,
                native_flow="new -> creation -> save -> regions -> pause -> map/options -> main -> load -> resume -> final blow -> ending -> credits -> load",
                regions=game.map_data.discovered_areas(), endings=endings, fresh_process_ending_loads=True,
                unique_reward=True, phase3_timer_roundtrip=timer, native_vent_damage=True,
                qa_seeds=["First two boss victories seeded", "Player Vigor=10000", "Third boss HP thresholds and final HP=1 seeded", "Teleports used for traversal", "All endings branched from pre-ending snapshot"],
                manual_full_playthrough=False, artifact_png_encoding="after QA measurement", quarantined=monitor.quarantined)
            (out / "campaign.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf8")
            if monitor.quarantined:
                raise RuntimeError("Build em quarentena; analisar perfis em " + str(out / "diagnostics.json"))
            print(json.dumps(dict(build_id=monitor.build_id, endings=endings, quarantined=False)))
    finally:
        app.destroy()


if __name__ == "__main__":
    main()
