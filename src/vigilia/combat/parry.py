"""Regras de janela de parry e sua tolerância de um passo."""

from enum import StrEnum, auto

from vigilia.core.timing import PARRY_WINDOW_STEPS


class ParryOutcome(StrEnum):
    SUCCESS = auto()
    LATE_BLOCK = auto()
    MISS = auto()


def parry_outcome(age: int) -> ParryOutcome:
    """A janela inclui os passos 0 a 11, com guarda residual no passo 12."""
    if 0 <= age < PARRY_WINDOW_STEPS:
        return ParryOutcome.SUCCESS
    return ParryOutcome.LATE_BLOCK if age == PARRY_WINDOW_STEPS else ParryOutcome.MISS
