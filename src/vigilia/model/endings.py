"""Escolha final persistente, independente de apresentação e motor."""

ENDINGS = ("maintain", "extinguish", "transform")
FINAL_BOSS = "last_ember_custodian"


def choose_ending(state, choice):
    if choice not in ENDINGS:
        raise ValueError("ending.invalid")
    if FINAL_BOSS not in state.defeated_bosses:
        raise ValueError("ending.locked")
    if state.ending and state.ending != choice:
        raise ValueError("ending.already_chosen")
    state.ending = choice
    return choice
