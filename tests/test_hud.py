"""Dano, estamina, almas e efeitos atualizam o HUD por consultas fake."""

from dataclasses import replace

from ui_fakes import BackendFake, QueryFake
from vigilia.core.views import BossView, StatusView
from vigilia.ui.hud import HUD


def test_hud_reflects_damage_stamina_souls_weapon_and_quick_item():
    backend, query = BackendFake(), QueryFake()
    hud = HUD(backend, query)
    hud.tick()
    query.vitals = replace(query.vitals, hp=70, stamina=55, souls=588, weapon="Machado +1")
    hud.tick()
    assert hud.hp.ratio == hud.stamina.ratio == .5
    assert "70 / 140" in hud.hp_text.value
    assert "588" in hud.souls.value and hud.weapon.value == "Machado +1"
    backend.updates.clear()
    hud.tick()
    assert not backend.updates


def test_boss_bar_only_exists_during_active_encounter_and_tracks_phase():
    backend, query = BackendFake(), QueryFake()
    hud = HUD(backend, query)
    hud.tick()
    assert not backend.nodes["hud.boss"]["visible"]
    query.boss = BossView("Vigia", 1600, 3200, 2)
    hud.tick()
    assert backend.nodes["hud.boss"]["visible"] and hud.boss_hp.ratio == .5
    assert "Vigia" in hud.boss_name.value and "2" in hud.boss_name.value
    query.boss = None
    hud.tick()
    assert not backend.nodes["hud.boss"]["visible"]


def test_status_icons_show_stacks_and_buildup_then_disappear():
    backend, query = BackendFake(), QueryFake()
    hud = HUD(backend, query)
    query.statuses = [StatusView("poison", "Veneno", "V", 3), StatusView("bleed", "Sangramento", "S", 0, 42)]
    hud.tick()
    assert "[V] 3×" in hud.statuses.value and "42%" in hud.statuses.value
    query.statuses.clear()
    hud.tick()
    assert not hud.statuses.value
