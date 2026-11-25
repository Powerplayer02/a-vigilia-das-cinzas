"""Optional dash/slide domain. No engine, rendering or audio imports."""
from dataclasses import dataclass
import math

from vigilia.core.events import DashStartedEvent, DashTrailEvent, SlideStartedEvent
from vigilia.core.mathx import Vec3
from vigilia.core.protocols import IAgileBody
from vigilia.core.timing import (FIXED_DT, DASH_STEPS, DASH_IFRAME_STEPS,
    DASH_RECHARGE_STEPS, SLIDE_STEPS, SLIDE_JUMP_BOOST_STEPS)
from vigilia.core.types import Action
from vigilia.model.snapshots import AdvancedMotionSnapshot

DASH_DISTANCE = 4.5
RUN_SPEED = 5.8
SLIDE_SPEED = RUN_SPEED * 1.4
SLIDE_STAMINA = 14
JUMP_STAMINA = 12


@dataclass(frozen=True, slots=True)
class MotionResult:
    velocity: Vec3
    state: str
    invulnerable: bool = False


class AdvancedMovement:
    def __init__(self, body: IAgileBody, *, emit=lambda event: None, entity_id=0):
        self.body, self.emit, self.entity_id = body, emit, entity_id
        self.mode, self.age = '', 0
        self.charges, self.recharge = 2, 0
        self.direction = Vec3()
        self.air_velocity, self.air_steps = Vec3(), 0
        self._kills = set()

    @property
    def dashing(self):
        return self.mode == 'dash'

    @property
    def sliding(self):
        return self.mode == 'slide'

    def before_combat(self, pressed):
        if self.dashing and pressed in (Action.LIGHT, Action.HEAVY, Action.PARRY, Action.CAST):
            self.cancel()
        return self.dashing

    def cancel(self):
        self.mode, self.age = '', 0
        self.air_velocity, self.air_steps = Vec3(), 0
        self.body.set_crouched(False)

    def on_kill(self, target):
        if target in self._kills:
            return
        self._kills.add(target)
        self.charges = min(2, self.charges + 1)
        if self.charges == 2:
            self.recharge = 0

    @staticmethod
    def direction8(held, forward, right):
        # Quantize camera-relative input. Keyboard and stick diagonals have equal speed.
        if math.hypot(held.move_x, held.move_y) < .001:
            return forward.flat().normalized()
        angle = math.atan2(held.move_x, held.move_y)
        angle = round(angle / (math.pi / 4)) * (math.pi / 4)
        return (forward * math.cos(angle) + right * math.sin(angle)).flat().normalized()

    def step(self, held, edge, forward, right, fighter, position, *, busy=False):
        if self.charges < 2:
            self.recharge += 1
            if self.recharge == DASH_RECHARGE_STEPS:
                self.charges += 1
                self.recharge = 0
        if not fighter.alive or fighter.stagger_steps:
            self.cancel()
            return None
        pressed = edge.action if edge is not None and edge.pressed else None
        if pressed == Action.ROLL and not busy:
            self.cancel()
            return None
        if self.body.crouched and not self.sliding:
            self.body.set_crouched(False)
        if pressed == Action.DASH and self.charges and not busy:
            self.cancel()
            self.charges -= 1
            self.mode, self.age = 'dash', 0
            self.direction = self.direction8(held, forward, right)
            self.emit(DashStartedEvent(self.entity_id, position, self.direction))
        elif pressed == Action.SLIDE and not self.mode and not busy and self.body.grounded():
            if Action.RUN in held.actions and math.hypot(held.move_x, held.move_y) > .001 and fighter.spend(SLIDE_STAMINA):
                self.body.set_crouched(True)
                self.mode, self.age = 'slide', 0
                self.direction = (forward * held.move_y + right * held.move_x).flat().normalized()
                self.emit(SlideStartedEvent(self.entity_id, position))
        if pressed == Action.JUMP and not busy and not self.dashing and self.body.grounded():
            was_slide, age, direction = self.sliding, self.age, self.direction
            if fighter.stamina >= JUMP_STAMINA and self.body.set_crouched(False) and self.body.jump(7):
                fighter.spend(JUMP_STAMINA)
                self.mode, self.age = '', 0
                if was_slide:
                    self.air_velocity = direction * (SLIDE_SPEED * (1 - age / SLIDE_STEPS) * 1.2)
                    self.air_steps = SLIDE_JUMP_BOOST_STEPS
        if self.dashing:
            age = self.age
            weight = 1 if age < 9 else (12 - age) / 4
            velocity = self.direction * (DASH_DISTANCE / (10.5 * FIXED_DT) * weight)
            if age % 2 == 0:
                self.emit(DashTrailEvent(position))
            self.age += 1
            if self.age == DASH_STEPS:
                self.mode, self.age = '', 0
            fighter.blocking = False
            return MotionResult(velocity, 'dashing', age < DASH_IFRAME_STEPS)
        if self.sliding:
            if Action.SLIDE not in held.actions:
                self.cancel()
                return None
            velocity = self.direction * (SLIDE_SPEED * (1 - self.age / SLIDE_STEPS))
            self.age += 1
            if self.age == SLIDE_STEPS:
                self.mode, self.age = '', 0
                self.body.set_crouched(False)
            fighter.blocking = False
            return MotionResult(velocity, 'sliding')
        if self.air_steps:
            self.air_steps -= 1
            return MotionResult(self.air_velocity, 'airborne')
        if self.body.crouched:
            return MotionResult((forward * held.move_y + right * held.move_x) * 1.55, 'sliding')
        return None

    def to_snapshot(self):
        return AdvancedMotionSnapshot(self.mode, self.age, self.charges, self.recharge,
            self.direction, self.body.crouched, self.air_velocity, self.air_steps)

    def from_snapshot(self, data):
        self._kills.clear()
        self.mode, self.age, self.charges, self.recharge = data.mode, data.age, data.charges, data.recharge
        self.direction, self.air_velocity, self.air_steps = data.direction, data.air_velocity, data.air_steps
        self.body.set_crouched(data.crouched)
