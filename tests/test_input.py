"""Verifica bordas de comando independentes de render e teclas remapeadas."""

from vigilia.core.timing import FIXED_DT, FixedClock
from vigilia.core.types import Action, InputEdge
from vigilia.engine.input import InputManager


def test_short_press_and_release_survive_a_slow_render_frame() -> None:
    source = InputManager()
    source.key("space", True)
    source.key("space", False)
    received = []
    alpha = FixedClock().advance(6 * FIXED_DT, lambda: received.append(source.next_edge()))
    assert received == [InputEdge(Action.ROLL, True), InputEdge(Action.ROLL, False), None, None, None, None]
    assert 0 <= alpha < 1e-8
    assert Action.ROLL not in source.held().actions


def test_rebinding_a_chord_and_releasing_the_modifier() -> None:
    source = InputManager()
    source.rebind(Action.ROLL, "shift-t")
    source.key("space", True)
    assert source.next_edge() is None
    source.key("lshift", True)
    assert source.next_edge() == InputEdge(Action.RUN, True)
    source.key("t", True)
    source.key("t", True)
    assert source.next_edge() == InputEdge(Action.ROLL, True)
    assert source.next_edge() is None
    source.key("lshift", False)
    assert source.next_edge() == InputEdge(Action.ROLL, False)
    assert source.next_edge() == InputEdge(Action.RUN, False)
    assert Action.ROLL not in source.held().actions


def test_small_analog_deflection_requires_neutral_after_menu_transition():
    from vigilia.engine.input import InputMode
    source = InputManager()
    source.poll_gamepad(frozenset(), 0, .24)
    assert source.held().move_y > 0
    source.set_mode(InputMode.MENU)
    source.set_mode(InputMode.GAMEPLAY)
    assert source.held().move_y == 0
    source.poll_gamepad(frozenset(), 0, 0)
    source.poll_gamepad(frozenset(), 0, .24)
    assert source.held().move_y > 0


def test_gamepad_button_edges_and_analog_held_state() -> None:
    source = InputManager()
    source.poll_gamepad(frozenset({"face_a"}), 0, 0.6)
    source.poll_gamepad(frozenset({"face_a"}), 0, 0.6)
    assert 0 < source.held().move_y < 0.6
    assert source.next_edge() == InputEdge(Action.ROLL, True)
    assert source.next_edge() is None
    source.poll_gamepad(frozenset(), 0, 0.04)
    assert source.held().move_y == 0
    assert source.next_edge() == InputEdge(Action.ROLL, False)


def test_46_gamepad_combat_profile_and_menu_buttons_do_not_conflict():
    from vigilia.engine.input import InputMode
    for button, action in (("face_a", Action.ROLL), ("face_b", Action.PARRY),
                           ("face_x", Action.INTERACT), ("rshoulder", Action.LIGHT),
                           ("right_trigger", Action.HEAVY), ("lshoulder", Action.BLOCK),
                           ("left_trigger", Action.CAST)):
        source = InputManager()
        source.poll_gamepad(frozenset({button}), 0, 0)
        assert source.next_edge() == InputEdge(action, True)
        assert source.next_edge() is None
        source.poll_gamepad(frozenset(), 0, 0)
        source.set_mode(InputMode.MENU)
        source.poll_gamepad(frozenset({"face_a"}), 0, 0)
        assert source.next_edge() is None
        assert source.menu_next_edge().action == Action.MENU_CONFIRM
