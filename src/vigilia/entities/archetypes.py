"""Construção de inimigos com dependências injetadas pela composição."""

from vigilia.core.mathx import Vec3, Transform
from vigilia.core.protocols import ICharacterBody
from vigilia.entities.components import (
    AIStateComponent, AttackIntent, BodyRef, EnemyTag, LockOnTarget, MovementIntent, NavAgentComponent,
)
from vigilia.entities.ecs import Entity, World


def make_enemy(world: World, profile_id: str, position: Vec3, body: ICharacterBody,
               fighter: object, patrol: tuple[Vec3, ...]) -> Entity:
    """Registra componentes sem importar regras de combate ou estados de IA."""
    return world.spawn(
        Transform(position), fighter, EnemyTag(profile_id), BodyRef(body),
        AIStateComponent(), NavAgentComponent(position, patrol, patrol_index=1 if len(patrol) > 1 else 0), MovementIntent(),
        AttackIntent(), LockOnTarget(),
    )
