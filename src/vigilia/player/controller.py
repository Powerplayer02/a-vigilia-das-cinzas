"""Movimento, corrida e esquiva da arena em passos fixos."""

import math
from enum import StrEnum, auto

from vigilia.core.mathx import Transform, Vec3, lerp_angle
from vigilia.core.protocols import ICharacterBody
from vigilia.core.timing import FIXED_DT, ROLL_STEPS_MID, BACKSTEP_STEPS
from vigilia.core.types import Action, HeldState, InputEdge
from vigilia.combat.fighter import Fighter
from vigilia.core.timing import ROLL_IFRAME_START, ROLL_IFRAME_END
from vigilia.model.inventory import RollTier
from vigilia.model.snapshots import MotionSnapshot


class PlayerState(StrEnum):
    IDLE = auto()
    WALKING = auto()
    RUNNING = auto()
    ROLLING = auto()
    BACKSTEP = auto()
    HIT_REACT = auto()
    DEATH = auto()
    KNOCKDOWN = auto()
    DASHING = auto()
    SLIDING = auto()
    AIRBORNE = auto()


class PlayerController:
    """Converte comandos em velocidade e mantém a pose do personagem."""

    ROLL_STEPS = ROLL_STEPS_MID
    BACKSTEP_STEPS = BACKSTEP_STEPS

    def __init__(self, body: ICharacterBody, transform: Transform, *, on_dodge=None) -> None:
        self.body = body
        self.on_dodge = on_dodge
        self.transform = transform
        self.state = PlayerState.IDLE
        self.velocity = Vec3()
        self._dodge_direction = Vec3()
        self._dodge_remaining = 0
        self.dodge_progress = 0.0
        self._dodge_total = ROLL_STEPS_MID
        self._dodge_speed = RollTier.MID.speed
        self.advanced = None

    @property
    def dodging(self) -> bool:
        return self._dodge_remaining > 0

    def update(self, held: HeldState, edge: InputEdge | None,
               forward: Vec3, right: Vec3, *, locked: bool, fighter: Fighter | None = None,
               busy: bool = False, mobility: RollTier = RollTier.MID) -> None:
        """Calcula a intenção do passo a partir do estado e de uma borda."""
        move = forward * held.move_y + right * held.move_x
        advanced = self.advanced.step(held, edge, forward, right, fighter,
            self.transform.position, busy=busy) if self.advanced is not None and fighter is not None else None
        if fighter is not None:
            fighter.invulnerable = False
            if not fighter.alive or fighter.stagger_steps:
                self._dodge_remaining = 0
                self.dodge_progress = 0
                self.velocity = Vec3()
                self.state = PlayerState.DEATH if not fighter.alive else (
                    PlayerState.KNOCKDOWN if fighter.knockdown_steps else PlayerState.HIT_REACT)
                return
        if advanced is not None:
            self._dodge_remaining, self.dodge_progress = 0, 0
            self.velocity, self.state = advanced.velocity, PlayerState(advanced.state)
            fighter.invulnerable = advanced.invulnerable
            facing = forward if locked else self.velocity
            if facing.length() > .001:
                self.transform.yaw = lerp_angle(self.transform.yaw, math.atan2(facing.x, facing.y), 14 * FIXED_DT)
            return
        if edge == InputEdge(Action.ROLL, True) and not self._dodge_remaining and not busy:
            if fighter is not None and not fighter.spend(24):
                edge = None
        if edge == InputEdge(Action.ROLL, True) and not self._dodge_remaining and not busy:
            if move.length() > 0.001:
                self.state = PlayerState.ROLLING
                self._dodge_direction = move.normalized()
                self._dodge_total = mobility.steps
                self._dodge_speed = mobility.speed
            else:
                self.state = PlayerState.BACKSTEP
                self._dodge_direction = (forward if locked else self.transform.forward()) * -1
                self._dodge_total = BACKSTEP_STEPS
                self._dodge_speed = 5.2
            self._dodge_remaining = self._dodge_total
            if self.on_dodge is not None:
                self.on_dodge()

        if self._dodge_remaining:
            if fighter is not None:
                fighter.blocking = False
            total, speed = self._dodge_total, self._dodge_speed
            self._dodge_remaining -= 1
            self.dodge_progress = 1 - self._dodge_remaining / total
            self.velocity = self._dodge_direction * (speed * (1 - 0.6 * self.dodge_progress))
            if fighter is not None:
                age = total - self._dodge_remaining - 1
                fighter.invulnerable = (self.state == PlayerState.ROLLING and
                                        ROLL_IFRAME_START <= age < ROLL_IFRAME_END)
        else:
            self.dodge_progress = 0
            running = Action.RUN in held.actions
            if busy:
                move = Vec3()
                running = False
            elif fighter is not None and fighter.blocking:
                move = move * .4
                running = False
            if running and fighter is not None:
                running = fighter.spend(14 * FIXED_DT) if move.length() > 0 else False
            self.velocity = move * (5.8 if running else 3.1)
            self.state = PlayerState.IDLE
            if move.length() > 0.001:
                self.state = PlayerState.RUNNING if running else PlayerState.WALKING

        facing = forward if locked else self.velocity
        if self.state == PlayerState.ROLLING:
            facing = self._dodge_direction
        if self.state == PlayerState.BACKSTEP and not locked:
            facing = self.transform.forward()
        if facing.length() > 0.001:
            yaw = math.atan2(facing.x, facing.y)
            self.transform.yaw = lerp_angle(self.transform.yaw, yaw, 14 * FIXED_DT)

    def apply_movement(self) -> None:
        """Entrega a intenção ao Bullet antes do passo de física."""
        self.body.set_velocity(self.velocity)

    def read_position(self) -> None:
        """Sincroniza a pose ECS com o resultado do Bullet."""
        self.transform.position = self.body.position()

    def to_snapshot(self) -> MotionSnapshot:
        """Expõe a pose e o estado de locomoção com timers em passos."""
        return MotionSnapshot(
            self.transform.position, self.transform.yaw, self.state.value, self.velocity,
            self._dodge_direction, self._dodge_remaining, self._dodge_total,
            self._dodge_speed, self.dodge_progress,
            self.advanced.to_snapshot() if self.advanced is not None else None,
        )

    def from_snapshot(self, snapshot: MotionSnapshot) -> None:
        """Reposiciona o corpo e restaura uma ação em curso."""
        self.transform.position, self.transform.yaw = snapshot.position, snapshot.yaw
        self.state, self.velocity = PlayerState(snapshot.state), snapshot.velocity
        self._dodge_direction = snapshot.dodge_direction
        self._dodge_remaining, self._dodge_total = snapshot.dodge_remaining, snapshot.dodge_total
        self._dodge_speed, self.dodge_progress = snapshot.dodge_speed, snapshot.dodge_progress
        self.body.teleport(snapshot.position)
        self.body.set_velocity(snapshot.velocity)
        if self.advanced is not None and snapshot.advanced is not None:
            self.advanced.from_snapshot(snapshot.advanced)
