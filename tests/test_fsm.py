"""Uma transição por passo, callbacks e timer de patrulha."""

from vigilia.ai.fsm import FixedStepFSM
from vigilia.core.types import AIMode
from vigilia.entities.components import AIStateComponent


class TestState:
    __test__ = False

    def __init__(self, mode, log, next_state=None):
        self.mode, self.log, self.next_state = mode, log, next_state

    def on_enter(self, context):
        self.log.append(("enter", self.mode))

    def on_exit(self, context):
        self.log.append(("exit", self.mode))

    def tick(self, context):
        self.log.append(("tick", self.mode))
        return self.next_state


def test_fsm_transitions_once_and_calls_exit_then_enter() -> None:
    log = []
    third = TestState(AIMode.CHASE, log)
    second = TestState(AIMode.PATROL, log, third)
    first = TestState(AIMode.IDLE, log, second)
    record = AIStateComponent()
    machine = FixedStepFSM(record, first)
    machine.tick(None)
    assert record.mode == AIMode.PATROL and record.age == 0
    assert log == [("tick", AIMode.IDLE), ("exit", AIMode.IDLE), ("enter", AIMode.PATROL)]
    machine.tick(None)
    assert record.mode == AIMode.CHASE


def test_forced_dead_state_preempts_attack_tick() -> None:
    log = []
    first = TestState(AIMode.ATTACK_WINDUP, log)
    dead = TestState(AIMode.DEAD, log)
    record = AIStateComponent()
    machine = FixedStepFSM(record, first)
    machine.tick(None, dead)
    assert record.mode == AIMode.DEAD
    assert ("tick", AIMode.ATTACK_WINDUP) not in log
