"""Transições e controladores de aplicação sem importar Panda3D."""

import pytest
from vigilia.core.app_state import AppStateMachine, CallbackController
from vigilia.core.events import EventBus, AppStateChangedEvent
from vigilia.core.types import AppState as S


def test_full_lifecycle_emits_one_event_per_transition_and_ticks_current_controller():
    bus, events, ticks = EventBus(), [], []
    bus.subscribe(AppStateChangedEvent, events.append)
    flow = AppStateMachine(bus)
    for state in S:
        flow.register(state, CallbackController(on_tick=lambda dt, state=state: ticks.append(state)))
    sequence = (S.MAIN_MENU, S.CHARACTER_CREATION, S.PLAYING, S.PAUSED, S.MAIN_MENU)
    for state in sequence:
        flow.transition(state)
        flow.tick(1 / 60)
    assert [event.current for event in events] == list(sequence)
    assert ticks == list(sequence) and not flow.simulating


def test_invalid_transition_is_atomic_and_quit_is_terminal():
    bus, events = EventBus(), []
    bus.subscribe(AppStateChangedEvent, events.append)
    flow = AppStateMachine(bus)
    with pytest.raises(ValueError):
        flow.transition(S.PAUSED)
    assert flow.current == S.BOOT and not events
    flow.transition(S.MAIN_MENU)
    flow.transition(S.QUIT)
    with pytest.raises(ValueError):
        flow.transition(S.PLAYING)


def test_options_return_to_their_origin_and_resume_clears_history():
    flow = AppStateMachine(EventBus())
    flow.transition(S.MAIN_MENU)
    flow.push(S.OPTIONS)
    flow.back()
    assert flow.current == S.MAIN_MENU
    flow.transition(S.PLAYING)
    flow.push(S.PAUSED)
    flow.push(S.OPTIONS)
    flow.back()
    assert flow.current == S.PAUSED
    flow.back()
    assert flow.simulating
