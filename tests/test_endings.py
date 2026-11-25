"""Versioned preboss states -> combat victory -> epilogue -> durable credits.

Physics and drawing use fakes in CI. tools/verify_endings.py repeats the
three cases with the native Game, Bullet, fog wall, altar and UI.
"""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from combat_fakes import ContactFake, PhysicsFake
from test_final_campaign import final_encounter
from ui_fakes import BackendFake
from vigilia.combat.events import DamageDealt
from vigilia.combat.hitbox import HURT_BONES
from vigilia.combat.orchestrator import CombatSystem
from vigilia.core.events import BossDefeatedEvent, EndingChosenEvent, SaveRequestedEvent
from vigilia.core.locale import Localizer
from vigilia.core.mathx import Transform, Vec3
from vigilia.core.types import AppState
from vigilia.game import Game
from vigilia.model.endings import ENDINGS, FINAL_BOSS, choose_ending
from vigilia.model.spells import SPELLS
from vigilia.model.world_state import WorldState
from vigilia.save.serializers import SaveFormatError, decode, encode
from vigilia.save.service import SaveService
from vigilia.ui.main_menu import Credits

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/saves'
CASES = tuple(zip(ENDINGS, ('a', 'b', 'c')))


def load_fixture(tmp_path, letter):
    source = FIXTURES / ('ending_' + letter + '_preboss.db')
    manifest = json.loads((FIXTURES / 'endings.json').read_text())
    expected = next(row['sha256'] for row in manifest['cases'] if row['file'] == source.name)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == expected
    target = tmp_path / source.name
    shutil.copy2(source, target)
    return SaveService(target)


@pytest.mark.parametrize('choice,letter', CASES)
def test_preboss_victory_epilogue_and_postcredits_roundtrip(tmp_path, choice, letter):
    service = load_fixture(tmp_path, letter)
    source = service.load(1)
    assert source.world.area_id == 'forno_da_vigilia'
    assert source.player.motion.position == Vec3(240, 10.5, 1.02)
    assert set(source.world.defeated_bosses) == {'warden_of_the_forge', 'abbess_of_the_tide'}
    assert len(source.world.discovered_areas) == 5 and len(source.world.visited_bonfires) >= 5
    assert not source.world.ending and not source.world.credits_seen
    assert source.world.bosses[0].fighter.hp == 5600
    state = WorldState(defeated_bosses=set(source.world.defeated_bosses))
    with pytest.raises(ValueError, match='ending.locked'):
        choose_ending(state, choice)
    e = final_encounter()
    keys = {e.player.id: 'player', e.entity.id: FINAL_BOSS}
    ids = {v: k for k, v in keys.items()}
    e.hero.from_snapshot(source.player.fighter, ids)
    e.boss.from_snapshot(source.world.bosses[0], ids, False)
    point = e.world.get(e.entity, Transform).position
    e.world.get(e.player, Transform).position = point + Vec3(0, -4)
    contacts = ContactFake()
    contacts.sync({(e.entity.id, bone): (point + Vec3(0, 0, .25), .7) for bone in HURT_BONES})
    resolver = CombatSystem(contacts, PhysicsFake(), e.bus)
    victories, damage, choices = [], [], []
    e.bus.subscribe(BossDefeatedEvent, victories.append)
    e.bus.subscribe(DamageDealt, damage.append)
    e.bus.subscribe(EndingChosenEvent, choices.append)
    e.bus.subscribe(BossDefeatedEvent, lambda event: state.defeated_bosses.add(event.boss_id))
    e.boss.start()
    for _ in range(181):
        e.boss.tick(e.world)
    # Shorten the fight only; damage, death timer and victory event remain real.
    e.fighter.hp, e.fighter.invulnerable = 1, False
    assert e.hero.start(SPELLS['ember_shard'].attack, aim=point + Vec3(0, 0, .25))
    for _ in range(300):
        resolver.resolve(e.world)
        e.hero.tick()
        e.boss.tick(e.world)
    assert len(victories) == 1 and any(event.target == e.entity.id for event in damage)
    assert e.boss.defeated and FINAL_BOSS in state.defeated_bosses
    game = Game.__new__(Game)
    game.active_area, game.active_slot = source.world.area_id, 1
    game._transform = Transform(Vec3(240, 35, 1.02))
    game.world_state, game._bus, game._pending_save = state, e.bus, None
    game.localizer = Localizer(ROOT / 'data/locale')
    game.flow = SimpleNamespace(current=AppState.PAUSED)
    game.flow.transition = lambda current: setattr(game.flow, 'current', current)
    def snapshot():
        return replace(source, player=replace(source.player, fighter=e.hero.to_snapshot(keys)),
            world=replace(source.world, ending=state.ending, credits_seen=state.credits_seen,
                defeated_bosses=tuple(sorted(state.defeated_bosses)),
                boss_phases={FINAL_BOSS: e.boss.phase}, bosses=(e.boss.to_snapshot(keys),)))
    def flush():
        service.save(1, snapshot())
        game._pending_save = None
    e.bus.subscribe(SaveRequestedEvent, lambda event: setattr(game, '_pending_save', event))
    game._flush_save = flush
    game._choose_ending(choice)
    assert game.flow.current == AppState.CREDITS and choices == [EndingChosenEvent(1, choice)]
    assert not service.load(1).world.credits_seen
    backend = BackendFake()
    credits = Credits(backend, SimpleNamespace(ending=lambda: state.ending),
        SimpleNamespace(execute=lambda command: game._back_from_front()))
    expected = backend.t('ending.' + choice + '.epilogue')
    assert expected in backend.nodes['front.body']['text']
    assert all(backend.t('ending.' + other + '.epilogue') not in backend.nodes['front.body']['text']
               for other in ENDINGS if other != choice)
    credits.back()
    assert game.flow.current == AppState.PLAYING
    service.close()
    reopened = SaveService(tmp_path / ('ending_' + letter + '_preboss.db'))
    after = reopened.load(1)
    assert after.world.ending == choice and after.world.credits_seen
    assert after.world.bosses[0].fighter is None and FINAL_BOSS in after.world.defeated_bosses
    assert after.player.character_name == source.player.character_name
    reopened.close()


@pytest.mark.parametrize('invalid', [None, 'keep', 'maintain|extinguish', ['maintain', 'extinguish']])
def test_invalid_or_double_decision_is_rejected_without_overwriting_save(tmp_path, invalid):
    service = load_fixture(tmp_path, 'a')
    original = service.load(1)
    state = WorldState(defeated_bosses={FINAL_BOSS})
    with pytest.raises(ValueError, match='ending.invalid'):
        choose_ending(state, invalid)
    assert not state.ending and service.load(1) == original
    with pytest.raises(SaveFormatError):
        service.save(1, replace(original, world=replace(original.world, ending=invalid)))
    assert service.load(1) == original
    service.close()


def test_no_decision_is_valid_until_altar_and_credits_require_decision(tmp_path):
    service = load_fixture(tmp_path, 'b')
    original = service.load(1)
    assert decode(original.version, original.timing_version, *encode(original)) == original
    with pytest.raises(SaveFormatError):
        service.save(1, replace(original, world=replace(original.world, credits_seen=True)))
    assert service.load(1) == original
    service.close()


@pytest.mark.parametrize('language', ['pt_BR', 'en_US'])
def test_three_epilogues_do_not_collide_in_either_language(language):
    localizer = Localizer(ROOT / 'data/locale', language)
    texts = [localizer.t('ending.' + choice + '.epilogue') for choice in ENDINGS]
    assert all(text and not text.startswith('ending.') for text in texts)
    assert len(set(texts)) == 3
