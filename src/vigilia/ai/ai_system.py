"""Percepção, FSM e navegação dos agentes em passos fixos."""

import math
import time

from vigilia.ai.behaviors import AIContext, Dead, Idle, Staggered
from vigilia.ai.enemy_profiles import PROFILES
from vigilia.ai.fsm import FixedStepFSM
from vigilia.ai.pathfinding import a_star, line_of_sight
from vigilia.combat.fighter import Fighter
from vigilia.core.mathx import Transform, Vec3
from vigilia.core.navigation import NavGrid
from vigilia.core.protocols import IPhysicsWorld
from vigilia.core.timing import REPATH_INTERVAL_STEPS
from vigilia.entities.components import (
    AIStateComponent, AttackIntent, EnemyTag, MovementIntent, NavAgentComponent,
)
from vigilia.entities.ecs import Entity, World


class AISystem:
    """Lê percepção e escreve intenções. As métricas não participam das decisões."""

    def __init__(self, grid: NavGrid, physics: IPhysicsWorld, target: Entity) -> None:
        self.grid, self.physics, self.target = grid, physics, target
        self._machines: dict[int, FixedStepFSM] = {}
        self.step = 0
        self.tick_seconds = 0.0
        self.tick_count = 0
        self.path_seconds = 0.0
        self.path_count = 0
        self._systems = []

    def add_system(self, system) -> None:
        """Registra outros controladores de IA na mesma etapa da simulação."""
        self._systems.append(system)

    def tick(self, world: World) -> None:
        started = time.perf_counter()
        for system in self._systems:
            system.tick(world)
        target = world.get(self.target, Transform)
        target_fighter = world.get(self.target, Fighter)
        assert target is not None and target_fighter is not None
        for entity, (transform, fighter, state, nav, movement, attack, tag) in world.query(
            Transform, Fighter, AIStateComponent, NavAgentComponent, MovementIntent, AttackIntent, EnemyTag,
        ):
            movement.velocity = Vec3()
            attack.definition = None
            profile = PROFILES[tag.profile_id]
            distance = (target.position - transform.position).length()
            visible = distance <= profile.detection_radius and self.physics.raycast(
                transform.position + Vec3(0, 0, .25), target.position + Vec3(0, 0, .20),
            ) is None
            context = AIContext(entity.id, transform, fighter, state, nav, movement, attack,
                                profile, self.target.id, target, visible, target_fighter.alive, self)
            if entity.id not in self._machines:
                self._machines[entity.id] = FixedStepFSM(state, Idle())
                nav.next_repath = self.step
            forced = Dead() if not fighter.alive else Staggered() if fighter.stagger_steps else None
            self._machines[entity.id].tick(context, forced)
        self.step += 1
        self.tick_count += 1
        self.tick_seconds += time.perf_counter() - started

    def move(self, context: AIContext, goal: Vec3) -> None:
        nav = context.nav
        actual_start = self.grid.to_cell(context.transform.position)
        start_cell, goal_cell = self.grid.nearest_walkable(context.transform.position), self.grid.nearest_walkable(goal)
        if start_cell is None or goal_cell is None:
            return
        changed = nav.goal is None or (goal - nav.goal).flat().length() > 1.0
        due = (self.step >= nav.next_repath and
               self.step % REPATH_INTERVAL_STEPS == context.entity_id % REPATH_INTERVAL_STEPS)
        if due and (changed or nav.waypoint >= len(nav.route)):
            started = time.perf_counter()
            nav.route = a_star(self.grid, self.grid.to_world(start_cell), self.grid.to_world(goal_cell))
            if actual_start != start_cell and nav.route:
                nav.route.insert(0, self.grid.to_world(start_cell))
            self.path_seconds += time.perf_counter() - started
            self.path_count += 1
            nav.waypoint, nav.goal = 0, goal
            nav.next_repath = self.step + REPATH_INTERVAL_STEPS
        if nav.waypoint >= len(nav.route):
            return
        point = nav.route[nav.waypoint]
        if (point - context.transform.position).flat().length() < .20:
            nav.waypoint += 1
            if nav.waypoint >= len(nav.route):
                return
            point = nav.route[nav.waypoint]
        # Um alvo que mudou de posição não torna válido atravessar uma quina.
        if self.grid.walkable(actual_start):
            clear = line_of_sight(self.grid, actual_start, self.grid.to_cell(point))
        else:
            clear = self.physics.sweep_sphere(context.transform.position, point, .39) is None
        if not clear:
            nav.route.clear()
            return
        direction = (point - context.transform.position).flat().normalized()
        context.movement.velocity = direction * context.profile.speed
        context.transform.yaw = math.atan2(direction.x, direction.y)

    def retreat_goal(self, context: AIContext) -> Vec3 | None:
        away = (context.transform.position - context.target.position).flat().normalized()
        right = Vec3(away.y, -away.x)
        for direction in (away, (away + right).normalized(), (away - right).normalized(), right, right * -1):
            point = context.transform.position + direction * 2.5
            cell = self.grid.to_cell(point)
            if self.grid.walkable(cell):
                return self.grid.to_world(cell)
        return None

    def reset(self, world: World, *, restore=True) -> None:
        """Retorna os agentes às posições de origem, com FSM e rotas novas."""
        self._machines.clear()
        for _, (transform, fighter, state, nav, movement, attack) in world.query(
            Transform, Fighter, AIStateComponent, NavAgentComponent, MovementIntent, AttackIntent,
        ):
            if restore:
                transform.position, transform.yaw = nav.home, math.pi
                fighter.restore()
            state.mode, state.age, state.combo_index = Idle.mode, 0, 0
            state.alerted, state.rewarded = False, not fighter.alive
            nav.route.clear()
            nav.waypoint, nav.patrol_index, nav.goal = 0, 1 if len(nav.patrol) > 1 else 0, None
            nav.next_repath = self.step
            movement.velocity, attack.definition = Vec3(), None
