"""Sistemas ECS independentes da implementação de física."""

from vigilia.core.mathx import Vec3
from vigilia.core.protocols import IContactVolumes
from vigilia.core.mathx import Transform
from vigilia.entities.components import BodyRef, MovementIntent
from vigilia.entities.ecs import World


class MovementSystem:
    """Aplica intenções e lê posições de todos os personagens pela mesma porta."""

    def apply(self, world: World) -> None:
        for _, (body, intent) in world.query(BodyRef, MovementIntent):
            body.body.set_velocity(intent.velocity)

    def read_back(self, world: World) -> None:
        for _, (transform, body) in world.query(Transform, BodyRef):
            transform.position = body.body.position()


class HitboxSyncSystem:
    """Sincroniza volumes já calculados a partir da pose do passo atual."""

    def __init__(self, contacts: IContactVolumes) -> None:
        self._contacts = contacts

    def sync(self, poses: dict[int, dict[str, tuple[Vec3, float]]]) -> None:
        """Entrega todos os volumes atuais ao adaptador, inclusive remoções."""
        self._contacts.sync({
            (entity_id, bone): volume
            for entity_id, volumes in poses.items()
            for bone, volume in volumes.items()
        })
