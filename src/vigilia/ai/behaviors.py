"""Estados reutilizáveis que escrevem intenções em vez de mover corpos."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

from vigilia.combat.fighter import Fighter
from vigilia.core.mathx import Transform, Vec3
from vigilia.core.timing import PATROL_IDLE_STEPS
from vigilia.core.types import AIMode
from vigilia.entities.components import AIStateComponent, AttackIntent, MovementIntent, NavAgentComponent
from vigilia.model.enemies import EnemyProfile


class Navigator(Protocol):
    def move(self, context: AIContext, goal: Vec3) -> None: ...
    def retreat_goal(self, context: AIContext) -> Vec3 | None: ...


@dataclass(slots=True)
class AIContext:
    entity_id: int
    transform: Transform
    fighter: Fighter
    state: AIStateComponent
    nav: NavAgentComponent
    movement: MovementIntent
    attack: AttackIntent
    profile: EnemyProfile
    target_id: int
    target: Transform
    visible: bool
    target_alive: bool
    navigator: Navigator

    @property
    def distance(self) -> float:
        return (self.target.position - self.transform.position).flat().length()

    def face_target(self) -> None:
        direction = self.target.position - self.transform.position
        self.transform.yaw = math.atan2(direction.x, direction.y)


class Behavior:
    def on_enter(self, context: AIContext) -> None:
        pass

    def on_exit(self, context: AIContext) -> None:
        pass


class Idle(Behavior):
    mode = AIMode.IDLE

    def tick(self, context: AIContext):
        if context.target_alive and (context.visible or context.state.alerted):
            context.state.alerted = True
            return Chase()
        if context.state.age + 1 >= PATROL_IDLE_STEPS:
            return Patrol()
        return None


class Patrol(Behavior):
    mode = AIMode.PATROL

    def tick(self, context: AIContext):
        if context.target_alive and context.visible:
            context.state.alerted = True
            return Chase()
        goal = context.nav.patrol[context.nav.patrol_index]
        if (context.transform.position - goal).flat().length() < .45:
            context.nav.patrol_index = (context.nav.patrol_index + 1) % len(context.nav.patrol)
            return Idle()
        context.navigator.move(context, goal)
        return None


class Chase(Behavior):
    mode = AIMode.CHASE

    def tick(self, context: AIContext):
        if not context.target_alive:
            context.state.alerted = False
            return Patrol()
        if context.profile.ranged and context.distance < context.profile.min_range:
            return Reposition()
        if context.visible and context.distance <= context.profile.attack_range:
            context.state.combo_index = 0
            return AttackWindup()
        context.navigator.move(context, context.target.position)
        return None


class Reposition(Behavior):
    mode = AIMode.REPOSITION

    def tick(self, context: AIContext):
        if not context.target_alive:
            return Patrol()
        context.face_target()
        if context.distance >= context.profile.min_range and context.visible:
            context.state.combo_index = 0
            return AttackWindup()
        goal = context.navigator.retreat_goal(context)
        if goal is None:
            context.state.combo_index = 0
            return AttackWindup() if context.visible else Chase()
        context.navigator.move(context, goal)
        return None


class AttackWindup(Behavior):
    mode = AIMode.ATTACK_WINDUP

    def on_enter(self, context: AIContext) -> None:
        context.face_target()
        context.attack.definition = context.profile.attacks[context.state.combo_index]
        context.attack.target = context.target_id
        context.attack.aim = context.target.position + Vec3(0, 0, .20)

    def tick(self, context: AIContext):
        attack = context.fighter.attack
        if attack is None or attack.age >= attack.definition.windup + attack.definition.active:
            return Recover()
        return None


class Recover(Behavior):
    mode = AIMode.RECOVER

    def tick(self, context: AIContext):
        if context.fighter.attack is not None:
            return None
        index = context.state.combo_index + 1
        if (index < len(context.profile.attacks) and context.visible and context.target_alive
                and context.distance <= context.profile.attack_range + .3):
            context.state.combo_index = index
            return AttackWindup()
        context.state.combo_index = 0
        return Reposition() if context.profile.ranged else Chase()


class Staggered(Behavior):
    mode = AIMode.STAGGERED

    def on_enter(self, context: AIContext) -> None:
        context.state.combo_index = 0
        context.attack.definition = None

    def tick(self, context: AIContext):
        return Chase() if context.fighter.stagger_steps == 0 else None


class Dead(Behavior):
    mode = AIMode.DEAD

    def on_enter(self, context: AIContext) -> None:
        context.fighter.attack = None
        context.attack.definition = None

    def tick(self, context: AIContext):
        return None
