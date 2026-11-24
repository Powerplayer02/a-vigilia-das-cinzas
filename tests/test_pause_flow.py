"""Pausa não chama a simulação e o input de menu não vaza ao personagem."""

from types import SimpleNamespace

from ui_fakes import BackendFake, QueryFake
from vigilia.core.types import GameState, Action
from vigilia.core.mathx import Transform, Vec3
from vigilia.core.timing import FixedClock
from vigilia.engine.input import InputManager, InputMode
from vigilia.engine.camera import CameraPose
from vigilia.entities.ecs import World
from vigilia.game import Game
from vigilia.player.controller import PlayerState
from vigilia.ui.menu_router import MenuRouter


def paused_game():
    game = Game.__new__(Game)
    game._app = SimpleNamespace(state=GameState.PLAYING)
    game._app.set_paused = lambda paused: setattr(game._app, "state", GameState.PAUSED if paused else GameState.PLAYING)
    game.input, game._clock = InputManager(), FixedClock()
    game._transform = game._previous = Transform()
    game._player = SimpleNamespace(dodge_progress=0, velocity=Vec3(), state=PlayerState.IDLE)
    game._previous_dodge = 0
    game._camera = SimpleNamespace(look=lambda *args: None, update=lambda *args: CameraPose(Vec3(), Vec3()))
    game._renderer = SimpleNamespace(draw=lambda *args: None)
    game._audio = SimpleNamespace(set_listener=lambda *args: None, update=lambda *args: None)
    game._particles = SimpleNamespace(update=lambda *args: None)
    game._polish = SimpleNamespace(update=lambda pose, dt, **kwargs: pose)
    game._footstep_position, game._footstep_distance = Vec3(), 0.
    game._target, game._switch_motion, game._enemies, game._world = None, 0, [], World()
    game._draw_combat = game._flush_save = lambda: None
    game.steps = 0
    game._fixed_step = lambda: setattr(game, "steps", game.steps + 1)
    query = QueryFake()
    game.menus = MenuRouter(BackendFake(), game.input, query, query, game)
    return game


def tap(game, key):
    game.keyboard(key, True)
    game.frame(1 / 60, (0, 0), (0, 0))
    game.keyboard(key, False)


def test_escape_pauses_before_next_fixed_step_and_resumes_without_catchup():
    game = paused_game()
    tap(game, "escape")
    assert game.input.mode == InputMode.MENU and game.menus.page == "pause"
    for _ in range(120):
        game.frame(1 / 30, (0, 0), (0, 0))
    assert game.steps == 0
    tap(game, "escape")
    assert game._app.state == GameState.PLAYING and game.steps == 0
    game.frame(1 / 60, (0, 0), (0, 0))
    assert game.steps == 1


def test_held_attack_and_movement_during_menu_are_suppressed_on_resume():
    game = paused_game()
    tap(game, "escape")
    game.keyboard("mouse1", True)
    game.keyboard("w", True)
    assert game.input.next_edge() is None and not game.input.held().actions
    tap(game, "escape")
    assert not game.input.held().actions and game.input.next_edge() is None
    game.keyboard("mouse1", False)
    game.keyboard("w", False)
    game.keyboard("mouse1", True)
    assert game.input.next_edge().action == Action.LIGHT


def test_inventory_shortcut_and_gamepad_navigation_back_and_resume():
    game = paused_game()
    tap(game, "i")
    assert game.menus.page == "inventory"
    game.gamepad(frozenset({"face_b"}), 0, 0)
    game.frame(1 / 60, (0, 0), (0, 0))
    assert game.menus.page == "pause"
    game.gamepad(frozenset(), 0, 0)
    game.gamepad(frozenset({"dpad_up"}), 0, 0)
    game.frame(1 / 60, (0, 0), (0, 0))
    game.gamepad(frozenset(), 0, 0)
    game.gamepad(frozenset({"dpad_up"}), 0, 0)
    game.frame(1 / 60, (0, 0), (0, 0))
    assert game.menus.shell.grid.index == 6
    game.gamepad(frozenset(), 0, 0)
    game.gamepad(frozenset({"face_a"}), 0, 0)
    game.frame(1 / 60, (0, 0), (0, 0))
    assert game._app.state == GameState.PLAYING
