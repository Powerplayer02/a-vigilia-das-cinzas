"""Composition emits presentation events without changing domain state."""

from types import SimpleNamespace
import pytest

from vigilia.core.events import EventBus, SfxRequestedEvent, UIFeedbackEvent, MusicChangeRequestedEvent, BossDefeatedEvent
from vigilia.core.mathx import Vec3, Transform
from vigilia.combat.events import ShotFired, ParrySucceeded, EntityDied
from vigilia.combat.fighter import Fighter
from vigilia.entities.ecs import World
from vigilia.entities.components import BossTag
from vigilia.game import Game
from vigilia.model.items import WEAPONS, PLAYER_WEAPON_IDS
from vigilia.model.attacks import AttackKind, StatusEffect
from vigilia.player.controller import PlayerState


@pytest.fixture
def game():
    g = Game.__new__(Game)
    g._sfx_enabled, g._bus, g._world = True, EventBus(), World()
    g._transform = Transform(Vec3())
    g._fighter = Fighter(0, WEAPONS["longsword"].instantiate())
    g._entity = g._world.spawn(g._transform, g._fighter)
    g._notify = lambda text: None
    g._sfx_tails, g._sfx_statuses = [], {}
    g._sfx_poll = g._sfx_status_tick = g._sfx_fire_age = 0.
    g._parry_sound_pending = g._parry_sound_success = False
    g._bonfires = SimpleNamespace(nearby=lambda p: None)
    g.sounds = []
    g._bus.subscribe(SfxRequestedEvent, g.sounds.append)
    return g


@pytest.mark.parametrize("weapon_id", PLAYER_WEAPON_IDS)
def test_each_player_weapon_uses_own_attack_palette(game, weapon_id):
    game._fighter.weapon = WEAPONS[weapon_id].instantiate()
    # The moveset controls definitions; the presentation callback only selects a cue.
    for kind, suffix in ((AttackKind.LIGHT_1, "light"), (AttackKind.HEAVY, "heavy"),
                         (AttackKind.RUNNING, "running"), (AttackKind.DASH_ATTACK, "dash_attack"),
                         (AttackKind.SLIDING, "slide_attack")):
        game._on_attack_sound(game._entity.id, SimpleNamespace(kind=kind))
        assert game.sounds[-1].kind == weapon_id + "_" + suffix


def test_failed_parry_has_one_failure_cue_and_success_suppresses_it(game):
    game._fighter.parry_step = 0
    game._presentation_sfx(.02, False)
    game._fighter.parry_step = -1
    game._presentation_sfx(.02, False)
    game._presentation_sfx(.02, False)
    assert [event.kind for event in game.sounds] == ["parry_fail"]
    game.sounds.clear()
    game._fighter.parry_step = 0
    game._presentation_sfx(.02, False)
    game._on_parry(ParrySucceeded(game._entity.id, 50))
    game._fighter.parry_step = -1
    game._presentation_sfx(.02, False)
    assert [event.kind for event in game.sounds] == ["parry"]


def test_status_presentation_never_ticks_or_changes_domain(game):
    game._fighter.status.active[StatusEffect.POISON] = 600
    before = (game._fighter.hp, game._fighter.status.active.copy())
    game._presentation_sfx(.11, False)
    game._presentation_sfx(1, False)
    assert [event.kind for event in game.sounds] == ["status_poison", "status_poison_tick"]
    assert (game._fighter.hp, game._fighter.status.active) == before
    game._fighter.status.active.clear()
    game._presentation_sfx(1, False)
    assert len(game.sounds) == 2


def test_spell_impact_and_delayed_dissipation_react_to_shot_event(game):
    traces = []
    game._renderer = SimpleNamespace(tracer=lambda *args, **kwargs: traces.append(args))
    game._on_shot(ShotFired(game._entity.id, Vec3(), Vec3(1, 2), "magic"))
    assert [event.kind for event in game.sounds] == ["magic_impact"]
    game._presentation_sfx(.2, True)
    assert [event.kind for event in game.sounds] == ["magic_impact", "magic_dissipate"]
    assert traces and game.sounds[-1].position == Vec3(1, 2)


@pytest.mark.parametrize("area,position,surface", [
    ("patio_da_vigilia", Vec3(), "stone"),
    ("catedral_submersa", Vec3(60, 4), "water"),
    ("pantano_das_cinzas", Vec3(120, 4), "mud"),
    ("ruinas_subterraneas", Vec3(180, 33), "wood"),
])
def test_four_surfaces_emit_distinct_steps(game, area, position, surface):
    game.active_area = area
    game._footstep_position = position - Vec3(0, .9)
    game._footstep_distance = 0.
    game._player = SimpleNamespace(state=PlayerState.WALKING)
    game._presentation_footsteps(position, False)
    assert game.sounds[-1].kind == "footstep_" + surface


def test_ui_widgets_emit_feedback_through_composition(game):
    from vigilia.ui.widgets import Button
    from ui_fakes import BackendFake
    game._bus.subscribe(UIFeedbackEvent, game._on_ui_feedback)
    backend = BackendFake()
    backend.feedback = lambda kind: game._bus.publish(UIFeedbackEvent(kind))
    commands = []
    button = Button(backend, "cue", "Confirm", (0, 0, 100, 30), lambda: commands.append(True))
    button.focus(True)
    button.activate()
    assert [event.kind for event in game.sounds] == ["ui_hover", "ui_click"]
    assert commands == [True]


def test_boss_death_cue_and_three_second_fade_begin_on_lethal_event(game):
    from vigilia.model.progression import Progression
    game._music_director = object()
    enemy = game._world.spawn(Transform(Vec3(0, 3)), Fighter(1, WEAPONS["longsword"].instantiate()), BossTag("last_ember_custodian"))
    game.world_state = SimpleNamespace(defeated_bosses=set())
    game.progression = Progression()
    game.boss = SimpleNamespace(entity=enemy, profile=SimpleNamespace(id="last_ember_custodian", name="Custódio", reward_item=""))
    game._sync_world_geometry = lambda: None
    music = []
    game._bus.subscribe(MusicChangeRequestedEvent, music.append)
    game._on_death(EntityDied(enemy.id))
    assert music[-1].fade_sec == 3
    assert [event.kind for event in game.sounds] == ["boss_death"]
    game._on_boss_defeated(BossDefeatedEvent("last_ember_custodian", 6000))
    assert [event.kind for event in game.sounds] == ["boss_death"]
