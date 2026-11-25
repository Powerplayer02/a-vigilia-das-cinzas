"""Optional dash/slide domain. No engine, rendering or audio imports."""
from dataclasses import dataclass
import math

from vigilia.core.events import (DashStartedEvent, DashTrailEvent, SlideStartedEvent,
    WallClingStartedEvent, WallJumpStartedEvent, SlamStartedEvent, SlamImpactEvent)
from vigilia.core.mathx import Vec3
from vigilia.core.protocols import IAgileBody, IPhysicsWorld
from vigilia.core.timing import (FIXED_DT, DASH_STEPS, DASH_IFRAME_STEPS,
    DASH_RECHARGE_STEPS, SLIDE_STEPS, SLIDE_JUMP_BOOST_STEPS,
    WALL_CLING_STEPS, WALL_JUMP_HEIGHT_MULTIPLIER, SLAM_SPEED, SLAM_RECOVERY_STEPS)
from vigilia.core.types import Action
from vigilia.model.snapshots import AdvancedMotionSnapshot
from vigilia.model.items import WEAPONS
from vigilia.model.attacks import AttackKind

DASH_DISTANCE = 4.5
RUN_SPEED = 5.8
SLIDE_SPEED = RUN_SPEED * 1.4
SLIDE_STAMINA = 14
JUMP_STAMINA = 12
SLAM_STAMINA = 18
SLAM_RADIUS = 2.5
SLAM_POISE = 60.


@dataclass(frozen=True, slots=True)
class MotionResult:
    velocity: Vec3
    state: str
    invulnerable: bool = False


class AdvancedMovement:
    def __init__(self, body: IAgileBody, *, emit=lambda event: None, entity_id=0,
                 physics: IPhysicsWorld | None = None):
        self.body, self.emit, self.entity_id = body, emit, entity_id
        self.physics = physics
        self.mode, self.age = '', 0
        self.charges, self.recharge = 2, 0
        self.direction = Vec3()
        self.air_velocity, self.air_steps = Vec3(), 0
        self._kills = set()
        self.vertical_control, self.vertical_speed = False, 0.
        self.wall_normal, self.used_walls = Vec3(), set()
        self.damage_interrupt = False
        self.used_surfaces = set()

    @property
    def dashing(self):
        return self.mode == 'dash'

    @property
    def sliding(self):
        return self.mode == 'slide'

    def before_combat(self, pressed):
        if self.dashing and pressed in (Action.LIGHT, Action.HEAVY, Action.PARRY, Action.CAST):
            self.cancel()
        return self.dashing or self.mode in ('wall_cling', 'slam', 'slam_recovery')

    def cancel(self):
        self.damage_interrupt = False
        self._release_vertical()
        self.mode, self.age = '', 0
        self.air_velocity, self.air_steps = Vec3(), 0
        self.body.set_crouched(False)

    def on_damage(self):
        if self.mode == 'wall_cling':
            self.damage_interrupt = True

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
        if self.damage_interrupt:
            self.cancel()
            return None
        pressed = edge.action if edge is not None and edge.pressed else None
        locked_air = self.mode in ('wall_cling', 'slam', 'slam_recovery')
        grounded = False if locked_air or (self.vertical_control and self.vertical_speed > 0) else self.body.grounded()
        if grounded and self.mode not in ('wall_cling', 'slam', 'slam_recovery') and self.vertical_speed <= 0:
            self.used_walls.clear()
            self.used_surfaces.clear()
            if self.vertical_control:
                self._release_vertical()
                self.air_velocity, self.air_steps = Vec3(), 0
        if pressed == Action.ROLL and not busy and self.mode not in ('wall_cling', 'slam', 'slam_recovery'):
            self.cancel()
            return None
        if self.body.crouched and not self.sliding:
            self.body.set_crouched(False)
        dash_direction = None
        if pressed == Action.DASH and self.mode not in ('slam', 'slam_recovery'):
            dash_direction = self.direction8(held, forward, right)
            if self.mode == 'wall_cling' and dash_direction.dot(self.wall_normal) < -.01:
                dash_direction = None
        if dash_direction is not None and self.charges and not busy:
            self.cancel()
            self.charges -= 1
            self.mode, self.age = 'dash', 0
            self.direction = dash_direction
            self.emit(DashStartedEvent(self.entity_id, position, self.direction))
        elif pressed == Action.SLIDE and not self.mode and not busy and self.body.grounded():
            if Action.RUN in held.actions and math.hypot(held.move_x, held.move_y) > .001 and fighter.spend(SLIDE_STAMINA):
                self.body.set_crouched(True)
                self.mode, self.age = 'slide', 0
                self.direction = (forward * held.move_y + right * held.move_x).flat().normalized()
                self.emit(SlideStartedEvent(self.entity_id, position))
        if (pressed == Action.SLAM and not busy and not grounded and self.physics is not None
                and self.mode not in ('slam', 'slam_recovery') and fighter.stamina >= SLAM_STAMINA
                and self.body.set_crouched(False)):
            fighter.spend(SLAM_STAMINA)
            self._own_vertical()
            self.mode, self.age, self.air_steps = 'slam', 0, 0
            self.air_velocity, self.vertical_speed = Vec3(), -SLAM_SPEED
            self.emit(SlamStartedEvent(self.entity_id, position))
        if self.mode == 'slam':
            fighter.blocking = False
            return self._slam_step(position, fighter)
        if self.mode == 'slam_recovery':
            fighter.blocking = False
            self.age += 1
            if self.age >= SLAM_RECOVERY_STEPS:
                self.mode, self.age = '', 0
                self._release_vertical()
            return MotionResult(Vec3(), 'slam_recovery')
        if self.mode == 'wall_cling':
            if pressed == Action.JUMP and not busy and fighter.spend(JUMP_STAMINA):
                self.mode, self.age = '', 0
                self.vertical_speed = 7 * math.sqrt(WALL_JUMP_HEIGHT_MULTIPLIER)
                self.air_velocity = self.wall_normal * RUN_SPEED
                self.emit(WallJumpStartedEvent(self.entity_id, position))
            else:
                self.age += 1
                if self.age >= WALL_CLING_STEPS:
                    self.mode, self.age = '', 0
                return MotionResult(Vec3(), 'wall_cling')
        movement = self.direction if self.dashing else (forward * held.move_y + right * held.move_x).flat()
        if movement.length() < .001 and (self.air_steps or self.vertical_control):
            movement = self.air_velocity.flat()
        if not grounded and self.mode not in ('slide',) and self._try_wall(position, movement):
            fighter.blocking = False
            return MotionResult(Vec3(), 'wall_cling')
        if pressed == Action.JUMP and not busy and self.mode in ('', 'slide') and grounded:
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
        if self.vertical_control:
            self.vertical_speed = max(-SLAM_SPEED, self.vertical_speed - 20 * FIXED_DT)
            return MotionResult(self.air_velocity + Vec3(0, 0, self.vertical_speed), 'airborne')
        if self.body.crouched:
            return MotionResult((forward * held.move_y + right * held.move_x) * 1.55, 'sliding')
        return None

    def _own_vertical(self):
        if not self.vertical_control:
            self.body.override_vertical(True)
            self.vertical_control = True

    def _release_vertical(self):
        if self.vertical_control:
            self.body.override_vertical(False)
            self.vertical_control = False
        self.vertical_speed = 0.

    def _try_wall(self, position, movement):
        if self.physics is None or movement.length() < .001:
            return False
        direction = movement.flat().normalized()
        hit = self.physics.raycast(position, position + direction * .5)
        if (hit is None or not 0 <= hit.distance <= .5001 or abs(hit.normal.z) > .25
                or hit.normal.dot(direction) >= -.5):
            return False
        normal = hit.normal.flat().normalized()
        key = (round(normal.x, 3), round(normal.y, 3), round(normal.z, 3), round(normal.dot(hit.point), 2))
        used = hit.surface_id in self.used_surfaces if hit.surface_id is not None else key in self.used_walls
        if used or not self.body.set_crouched(False):
            return False
        self._own_vertical()
        self.used_walls.add(key)
        if hit.surface_id is not None:
            self.used_surfaces.add(hit.surface_id)
        self.mode, self.age, self.wall_normal = 'wall_cling', 1, normal
        self.air_velocity, self.air_steps, self.vertical_speed = Vec3(), 0, 0.
        self.emit(WallClingStartedEvent(self.entity_id, position, normal))
        return True

    def _slam_step(self, position, fighter):
        offset = self.body.floor_offset
        hit = self.physics.raycast(position, position - Vec3(0, 0, offset + SLAM_SPEED * FIXED_DT + .04))
        support = self.body.ground_hit(SLAM_SPEED * FIXED_DT + .04)
        if support is not None and (hit is None or
                support.point.z + support.support_offset > hit.point.z + offset):
            hit, offset = support, support.support_offset
        if hit is None or hit.normal.z <= .5:
            return MotionResult(Vec3(0, 0, -SLAM_SPEED), 'slamming')
        distance = position.z - offset - hit.point.z
        if distance > SLAM_SPEED * FIXED_DT + .04:
            return MotionResult(Vec3(0, 0, -SLAM_SPEED), 'slamming')
        packet = WEAPONS[fighter.weapon.spec_id].attack(AttackKind.LIGHT_1).packet
        kinds = ('physical_slash', 'physical_strike', 'physical_pierce', 'fire', 'magic', 'holy')
        parts = tuple((kind, getattr(packet, kind) * .4) for kind in kinds if getattr(packet, kind))
        self.emit(SlamImpactEvent(hit.point, SLAM_RADIUS, sum(value for _, value in parts),
            SLAM_POISE, self.entity_id, fighter.team, parts))
        self.mode, self.age, self.vertical_speed = 'slam_recovery', 1, 0.
        return MotionResult(Vec3(0, 0, max(-SLAM_SPEED, min(0., -distance / FIXED_DT))), 'slam_recovery')

    def to_snapshot(self):
        return AdvancedMotionSnapshot(self.mode, self.age, self.charges, self.recharge,
            self.direction, self.body.crouched, self.air_velocity, self.air_steps,
            self.vertical_control, self.vertical_speed, self.wall_normal, tuple(sorted(self.used_walls)),
            self.damage_interrupt, tuple(sorted(self.used_surfaces)))

    def from_snapshot(self, data):
        self._kills.clear()
        self.mode, self.age, self.charges, self.recharge = data.mode, data.age, data.charges, data.recharge
        self.direction, self.air_velocity, self.air_steps = data.direction, data.air_velocity, data.air_steps
        self.body.set_crouched(data.crouched)
        self.vertical_speed, self.wall_normal = data.vertical_speed, data.wall_normal
        self.used_walls = set(data.used_walls)
        self.damage_interrupt = data.damage_interrupt
        self.used_surfaces = set(data.used_surfaces)
        if data.vertical_control:
            self._own_vertical()
        else:
            self._release_vertical()
