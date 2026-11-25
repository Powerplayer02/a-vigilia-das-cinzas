"""Relógio de simulação com interpolação para apresentação."""

from collections.abc import Callable

FIXED_HZ = 60
FIXED_DT = 1.0 / FIXED_HZ
PARRY_WINDOW_STEPS = 12
PARRY_WINDOW_SEC = PARRY_WINDOW_STEPS / FIXED_HZ
ROLL_IFRAME_START = 2
ROLL_IFRAME_END = 14
STAGGER_STEPS_LIGHT = 24
STAGGER_STEPS_HEAVY = 42
TIMING_VERSION = 1
ROLL_STEPS_FAST = 27
ROLL_STEPS_MID = 33
ROLL_STEPS_HEAVY = 45
BACKSTEP_STEPS = 19
PARRY_RECOVERY_STEPS = 28
RIPOSTE_STEPS = 90
STAMINA_REGEN_DELAY_STEPS = 40
HIT_REACT_STEPS = 18
CHARGE_STEPS = 36
RESPAWN_STEPS = 120
TRAINING_COOLDOWN_STEPS = 105
TRAINING_INITIAL_WAIT_STEPS = 100
POISON_STEPS = 12 * FIXED_HZ
FROST_STEPS = 7 * FIXED_HZ
PATROL_IDLE_STEPS = 90
STAGGER_COOLDOWN_STEPS = 60
REPATH_INTERVAL_STEPS = 15
TARGET_SWITCH_STEPS = 15
KNOCKDOWN_STEPS = 60
PHASE_TRANSITION_STEPS = 90
BOSS_RIPOSTE_STEPS = 240
DASH_STEPS = 12
DASH_IFRAME_STEPS = 6
DASH_RECHARGE_STEPS = 72
DASH_TRAIL_STEPS = 15
SLIDE_STEPS = 36
SLIDE_ATTACK_WINDUP = 9
SLIDE_ATTACK_ACTIVE = 5
SLIDE_ATTACK_RECOVERY = 20
SLIDE_JUMP_BOOST_STEPS = 24
WALL_CLING_STEPS = 24
SLAM_RECOVERY_STEPS = 8
SLAM_SPEED = 18.
WALL_JUMP_HEIGHT_MULTIPLIER = 1.3
MOMENTUM_STEPS = 24
COYOTE_STEPS = 6
JUMP_BUFFER_STEPS = 6
DASH_ATTACK_WINDUP = 8
DASH_ATTACK_ACTIVE = 6
DASH_ATTACK_RECOVERY = 24

assert MOMENTUM_STEPS * FIXED_DT == .4
assert COYOTE_STEPS * FIXED_DT == .1
assert JUMP_BUFFER_STEPS * FIXED_DT == .1

assert WALL_CLING_STEPS * FIXED_DT == .4
assert SLAM_RECOVERY_STEPS * FIXED_DT == 8 / 60

assert DASH_STEPS * FIXED_DT == .2
assert DASH_IFRAME_STEPS * FIXED_DT == .1
assert DASH_RECHARGE_STEPS * FIXED_DT == 1.2
assert SLIDE_STEPS * FIXED_DT == .6

assert PARRY_WINDOW_STEPS * FIXED_DT == PARRY_WINDOW_SEC
assert ROLL_IFRAME_END - ROLL_IFRAME_START == 12


class FixedClock:
    """Converte tempo de render em passos iguais, limitando a recuperação."""

    def __init__(self) -> None:
        self._elapsed = 0.0

    def advance(self, elapsed: float, step: Callable[[], None]) -> float:
        """Executa os passos disponíveis e retorna a fração para interpolar."""
        # Um travamento longo não deve produzir outro quadro longo.
        self._elapsed += max(0.0, min(elapsed, 0.25))
        while self._elapsed + 1e-10 >= FIXED_DT:
            self._elapsed = max(0.0, self._elapsed - FIXED_DT)
            step()
        return self._elapsed / FIXED_DT

    def reset(self) -> None:
        """Descarta o tempo pendente, por exemplo ao pausar."""
        self._elapsed = 0.0
