"""FSM com uma transição por passo e callbacks de entrada e saída."""

from __future__ import annotations

from typing import Protocol, TYPE_CHECKING

from vigilia.core.types import AIMode
from vigilia.entities.components import AIStateComponent

if TYPE_CHECKING:
    from vigilia.ai.behaviors import AIContext


class State(Protocol):
    mode: AIMode

    def on_enter(self, context: AIContext) -> None: ...
    def on_exit(self, context: AIContext) -> None: ...
    def tick(self, context: AIContext) -> State | None: ...


class FixedStepFSM:
    """Mantém os timers no componente consultável pelo ECS."""

    def __init__(self, record: AIStateComponent, state: State) -> None:
        self.record, self.state = record, state
        self.record.mode = state.mode
        self.record.age = 0

    def tick(self, context: AIContext, forced: State | None = None) -> None:
        """Executa uma ação do estado ou uma única transição prioritária."""
        if forced is not None and forced.mode != self.state.mode:
            target = forced
        else:
            target = self.state.tick(context)
        self.record.age += 1
        if target is not None and target.mode != self.state.mode:
            self.state.on_exit(context)
            self.state = target
            self.record.mode, self.record.age = target.mode, 0
            target.on_enter(context)
