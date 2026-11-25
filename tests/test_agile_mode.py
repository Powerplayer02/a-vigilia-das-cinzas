from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import pytest
from advanced_fakes import scene
from test_save import full_snapshot
from vigilia.core.config import Config, load_config
from vigilia.core.settings import SettingsStore
from vigilia.core.types import Action, InputEdge
from vigilia.model.items import AXE_SPEC
from vigilia.engine.input import InputManager, InputMode
from vigilia.save.serializers import encode, decode, SaveFormatError
from vigilia.save.service import SaveService


def test_off_ignores_new_keys_and_gamepad_without_delaying_light_attack():
    source=InputManager()
    source.key('alt',True);source.key('v',True);source.key('b',True)
    source.poll_gamepad(frozenset({'dpad_right','dpad_down','dpad_up'}),0,0)
    assert source.next_edge() is None
    source.key('mouse1',True)
    assert source.next_edge()==InputEdge(Action.LIGHT,True)


def test_on_supports_remapped_keys_pad_and_menu_suppression():
    source=InputManager();source.set_agile_enabled(True)
    source.rebind(Action.DASH,'t')
    source.key('t',True)
    assert source.next_edge()==InputEdge(Action.DASH,True)
    source.set_mode(InputMode.MENU);source.set_mode(InputMode.GAMEPLAY)
    assert source.next_edge() is None
    source.key('t',False);source.poll_gamepad(frozenset({'dpad_right'}),0,0)
    assert source.next_edge()==InputEdge(Action.DASH,True)


def test_config_defaults_off_and_rejects_non_boolean(tmp_path):
    path=tmp_path/'config.toml'
    path.write_text('[movement]\nultrakill_style = true\n')
    assert load_config(path).ultrakill_style
    assert not Config().ultrakill_style
    path.write_text('[movement]\nultrakill_style = "yes"\n')
    with pytest.raises(ValueError):load_config(path)


def test_settings_toggle_roundtrips_without_changing_remaps(tmp_path):
    path=tmp_path/'options.toml'
    store=SettingsStore(path,Config());store.rebind('dash','t')
    store.set('ultrakill_style',True)
    loaded=SettingsStore(path,Config())
    assert loaded.options.config.ultrakill_style
    assert loaded.options.config.bindings[Action.DASH]=='t'
    loaded.reset('controls')
    assert not loaded.options.config.ultrakill_style


@pytest.mark.parametrize('sliding',[False,True])
def test_save_preserves_mode_charges_timers_capsule_and_slide_attack(tmp_path,sliding):
    from test_slide import SLIDING
    s=scene()
    s.step(Action.SLIDE,SLIDING) if sliding else s.step(Action.DASH)
    if sliding:s.step(Action.LIGHT,SLIDING)
    original=full_snapshot()
    # Match catalog/stats/inventory of the existing known-valid axe snapshot.
    s.fighter.weapon=AXE_SPEC.instantiate(2)
    s.combat.equip(s.fighter.weapon)
    if sliding:s.fighter.attack=None;s.step(Action.LIGHT,SLIDING)
    snapshot=replace(original,player=replace(original.player,agile_movement=True,
        motion=s.player.to_snapshot(),fighter=replace(original.player.fighter,
            attack=s.fighter.to_snapshot({}).attack if sliding else None)))
    service=SaveService(tmp_path/'agile.db');service.save(1,snapshot);loaded=service.load(1)
    assert loaded==snapshot and loaded.player.motion.advanced.charges==s.movement.charges
    s.movement.cancel();s.player.from_snapshot(loaded.player.motion)
    assert s.player.to_snapshot()==loaded.player.motion
    assert s.body.crouched==sliding
    service.close()


@pytest.mark.parametrize('charges',[-1,3,True])
def test_corrupt_charge_state_is_rejected(charges):
    s=scene();s.step(Action.DASH)
    original=full_snapshot()
    motion=replace(s.player.to_snapshot(),advanced=replace(s.movement.to_snapshot(),charges=charges))
    with pytest.raises(SaveFormatError):encode(replace(original,player=replace(original.player,
        agile_movement=True,motion=motion)))
