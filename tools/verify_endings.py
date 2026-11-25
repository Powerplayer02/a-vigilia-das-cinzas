"""Three independent synthetic pre-boss saves; real native victory/altar/credits flow.

This verifies branching and persistence, not balance. Final blow uses HP=1.
Run --generate-fixtures only when intentionally replacing the versioned fixtures.
"""
import argparse
from contextlib import ExitStack
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from panda3d.core import Filename
from vigilia.combat.events import DamageDealt
from vigilia.core.config import Config
from vigilia.core.events import EndingChosenEvent
from vigilia.core.mathx import Transform, Vec3
from vigilia.core.types import AppState
from vigilia.core.views import UICommand, UICommandKind as C
from vigilia.engine.app import ArenaApp
from vigilia.game import Game
from vigilia.model.endings import ENDINGS, FINAL_BOSS
from vigilia.world.bonfire import BONFIRES
from vigilia.save.service import SaveService

FIXTURES = ROOT / 'tests/fixtures/saves'
CASES = dict(zip(ENDINGS, ('a', 'b', 'c')))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generate-fixtures', action='store_true')
    parser.add_argument('--case', choices=ENDINGS)
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/5.5/endings')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if not args.case and not args.generate_fixtures:
        for choice in ENDINGS:
            subprocess.run([sys.executable, __file__, '--case', choice, '--output', str(args.output)], check=True)
        reports = [json.loads((args.output / (c + '.json')).read_text(encoding='utf8')) for c in ENDINGS]
        assert len({r['epilogue'] for r in reports}) == 3
        (args.output / 'matrix.json').write_text(json.dumps(reports, indent=2, ensure_ascii=False), encoding='utf8')
        print('Three independent native ending flows passed')
        return
    app = ArenaApp(Config(vsync=False), window_type='offscreen')
    try:
        with tempfile.TemporaryDirectory(prefix='vigilia-endings-') as temporary, ExitStack() as cleanup:
            base = Path(temporary)
            path = base / 'campaign.db'
            if args.case:
                source = FIXTURES / ('ending_' + CASES[args.case] + '_preboss.db')
                before = hashlib.sha256(source.read_bytes()).hexdigest()
                shutil.copy2(source, path)
            game = Game(app, Config(vsync=False), ROOT / 'assets', front_end=True,
                save_path=path, settings_path=base / 'options.toml', enemy_count=3)
            cleanup.callback(game.close)
            app.start(game)
            app.taskMgr.remove('vigilia-update')
            def frames(n=1):
                for _ in range(n):
                    game.frame(1/60, (0, 0), (0, 0))
            def warp(point):
                game._player.body.teleport(point)
                game._transform.position = point
                game._previous = Transform(point)
            def tap(key):
                game.keyboard(key, True)
                frames()
                game.keyboard(key, False)
                frames()
            if args.generate_fixtures:
                game.execute(UICommand(C.NEW_GAME))
                game.execute(UICommand(C.SELECT_NEW_SLOT, '1'))
                error = game.execute(UICommand(C.CREATE_CHARACTER, json.dumps(dict(
                    name='Preboss QA', class_id='mage', allocation={'vigor': 10}, slot=1))))
                assert not error, error
                game.change_area('forno_da_vigilia', Vec3(240, 10.5, 1.02), stash=False, restore=False)
                game.world_state.defeated_bosses.update(('warden_of_the_forge', 'abbess_of_the_tide'))
                game.world_state.discovered_areas.update(p.stem for p in (ROOT / 'data/areas').glob('*.toml'))
                game.world_state.visited_bonfires.update(BONFIRES)
                game.world_state.last_bonfire = 'forno_limiar'
                snapshot = game.build_snapshot()
                assert FINAL_BOSS not in snapshot.world.defeated_bosses and not snapshot.world.ending
                assert snapshot.world.bosses[0].fighter.hp == 5600
                FIXTURES.mkdir(parents=True, exist_ok=True)
                records = []
                for choice, letter in CASES.items():
                    target = FIXTURES / ('ending_' + letter + '_preboss.db')
                    assert not target.exists(), 'Remove fixtures explicitly before intentional regeneration'
                    fixture = replace(snapshot, player=replace(snapshot.player, character_name='Ending ' + letter.upper() + ' QA'))
                    with ExitStack() as stack:
                        service = SaveService(target)
                        stack.callback(service.close)
                        service.save(1, fixture)
                        with service.repository.database.connect() as connection:
                            connection.execute('PRAGMA wal_checkpoint(TRUNCATE)')
                    records.append(dict(file=target.name, choice_after_victory=choice,
                        sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
                (FIXTURES / 'endings.json').write_text(json.dumps(dict(
                    source='Synthetic native Game snapshots; production class/boss stats; not historical player saves',
                    differentiator='Only intended choice in this manifest. No ending selected before victory.',
                    prior_bosses=['warden_of_the_forge', 'abbess_of_the_tide'], final_boss_alive=True, cases=records), indent=2), encoding='utf8')
                return
            game.execute(UICommand(C.CONTINUE))
            error = game.execute(UICommand(C.LOAD_SLOT, '1'))
            assert not error, error
            assert not game.boss.active and game.boss.fighter.hp == 5600
            assert FINAL_BOSS not in game.world_state.defeated_bosses and not game.world_state.ending
            events, damage = [], []
            game._bus.subscribe(EndingChosenEvent, events.append)
            game._bus.subscribe(DamageDealt, damage.append)
            tap('f')
            frames(181)
            assert game.boss.active
            # Deterministic functional helper: shorten this fight, without emitting a victory event.
            game.boss.fighter.hp = 1
            game.boss.fighter.invulnerable = False
            game.boss.intro_remaining = game.boss.transition_remaining = 0
            point = game._world.get(game.boss.entity, Transform).position
            warp(point + Vec3(0, -4, 0))
            game._target = game.boss.entity
            for _ in range(4):
                tap('e')
                frames(100)
                if not game.boss.fighter.alive:
                    break
            frames(250)
            assert any(e.target == game.boss.entity.id for e in damage)
            assert game.boss.defeated and FINAL_BOSS in game.world_state.defeated_bosses
            assert game.inventory.items['ember_heart'] == 1
            warp(Vec3(240, 35, 1.02))
            tap('f')
            assert game.menus.page == 'ending'
            ui = game.menus.content
            ui.grid.select(ENDINGS.index(args.case))
            ui.confirm()
            assert not game.world_state.ending  # Review is not confirmation.
            ui.grid.select(1)
            ui.confirm()
            assert game.flow.current == AppState.CREDITS
            epilogue = game.localizer.t('ending.' + args.case + '.epilogue')
            assert epilogue in game.ui_backend.labels['front.body'].get_text()
            assert len(events) == 1 and events[0].choice == args.case
            frames(18)  # Present credits after the checkpoint cover and UI transition.
            app.graphicsEngine.render_frame()
            assert app.win.save_screenshot(Filename.from_os_specific(str(args.output / (args.case + '.png'))))
            game.execute(UICommand(C.MAIN_MENU))
            game.execute(UICommand(C.CONTINUE))
            game.execute(UICommand(C.LOAD_SLOT, '1'))
            assert game.flow.current == AppState.CREDITS and not game.world_state.credits_seen
            game.execute(UICommand(C.BACK))
            assert game.flow.current == AppState.PLAYING and game.world_state.credits_seen
            game.execute(UICommand(C.MAIN_MENU))
            game.execute(UICommand(C.CONTINUE))
            game.execute(UICommand(C.LOAD_SLOT, '1'))
            assert game.flow.current == AppState.PLAYING and game.world_state.ending == args.case
            check = "import sys;sys.path.insert(0,sys.argv[1]);from pathlib import Path;from vigilia.save.service import SaveService;s=SaveService(Path(sys.argv[2])).load(1);assert s.world.ending==sys.argv[3] and s.world.credits_seen;assert 'panda3d.core' not in sys.modules"
            subprocess.run([sys.executable, '-c', check, str(ROOT / 'src'), str(path), args.case], check=True, capture_output=True)
            assert hashlib.sha256(source.read_bytes()).hexdigest() == before
            result = dict(choice=args.case, preboss_fixture=source.name, epilogue=epilogue,
                final_boss_alive_on_load=True, real_spell_damage=True, reward_count=1,
                ending_event=events[0].choice, unacknowledged_credits_reopened=True,
                postcredits_persisted=True, fresh_process_load=True, source_unchanged=True,
                qa_seeds=['Synthetic preboss fixture', 'Final blow HP=1', 'Teleport after entering fog'],
                manual_balance_certified=False)
            (args.output / (args.case + '.json')).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf8')
    finally:
        app.destroy()


if __name__ == '__main__':
    main()
