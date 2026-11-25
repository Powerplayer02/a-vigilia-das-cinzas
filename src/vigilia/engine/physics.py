"""Adaptador Panda3D Bullet para cenário, personagem e consultas espaciais."""

from dataclasses import dataclass
import math
from collections.abc import Sequence

from panda3d.bullet import (
    ZUp, BulletBoxShape, BulletCapsuleShape, BulletCharacterControllerNode,
    BulletRigidBodyNode, BulletSphereShape, BulletWorld, BulletGhostNode,
)
from panda3d.core import BitMask32, LPoint3f, LVector3f, NodePath, TransformState

from vigilia.core.mathx import Vec3
from vigilia.core.types import RayHit, VolumeRayHit

_WORLD = BitMask32.bit(0)
_CHARACTERS = BitMask32.bit(1)


def to_point(vector: Vec3) -> LPoint3f:
    """Converte coordenadas puras em um ponto do scene graph."""
    return LPoint3f(vector.x, vector.y, vector.z)


def _from_panda(vector: LVector3f | LPoint3f) -> Vec3:
    return Vec3(vector.x, vector.y, vector.z)


@dataclass(slots=True)
class CharacterBody:
    """Cápsula Bullet controlada por velocidade de gameplay."""

    node: BulletCharacterControllerNode
    path: NodePath
    world: BulletWorld
    active: bool = True
    radius: float = .39
    height: float = 1.78
    crouched: bool = False
    _standing: tuple | None = None
    _low: tuple | None = None
    _stand_query: NodePath | None = None
    vertical_override: bool = False
    _air: tuple | None = None

    @property
    def floor_offset(self):
        return self.height / 2 - .04

    def set_velocity(self, velocity: Vec3) -> None:
        """Define a velocidade em coordenadas mundiais."""
        self.node.set_linear_movement(LVector3f(velocity.x, velocity.y, velocity.z), False)

    def position(self) -> Vec3:
        """Lê a posição do centro da cápsula."""
        position = _from_panda(self.path.get_pos())
        return position + Vec3(0, 0, self.height / 4) if self.crouched else position

    def teleport(self, position: Vec3) -> None:
        """Reposiciona a cápsula para reiniciar o exercício."""
        self.set_velocity(Vec3())
        self.path.set_pos(to_point(position - Vec3(0, 0, self.height / 4) if self.crouched else position))

    def grounded(self) -> bool:
        if self.vertical_override:
            return self.ground_hit(.06) is not None
        return self.node.is_on_ground()

    def ground_hit(self, distance: float) -> RayHit | None:
        """Find walkable support, including actors and the capsule's rounded edge."""
        point, closest, closest_drop = self.position(), None, float('inf')
        # Eight rim probes cover ledges where the center ray misses the floor.
        probes = [(0., 0.)] + [(self.radius * .7 * math.cos(i * math.pi / 4),
            self.radius * .7 * math.sin(i * math.pi / 4)) for i in range(8)]
        for x, y in probes:
            offset = self.floor_offset - self.radius + math.sqrt(self.radius ** 2 - x*x - y*y)
            start = point + Vec3(x, y, 0)
            result = self.world.ray_test_all(to_point(start),
                to_point(start - Vec3(0, 0, offset + distance)), _WORLD | _CHARACTERS)
            for hit in result.get_hits():
                if hit.get_node() == self.node or hit.get_hit_normal().z <= .5:
                    continue
                surface = _from_panda(hit.get_hit_pos())
                drop = point.z - offset - surface.z
                if drop < closest_drop:
                    closest_drop = drop
                    closest = RayHit(surface, _from_panda(hit.get_hit_normal()),
                        (start - surface).length(), support_offset=offset)
        return closest

    def override_vertical(self, enabled: bool) -> None:
        """Use a gravity-free cached motor for cling/slam; reset native fall state on exit."""
        if enabled == self.vertical_override:
            return
        anchor = self.position()
        if enabled:
            if self.crouched and not self.set_crouched(False):
                raise ValueError('movement.blocked')
            if self._standing is None:
                self._standing = self.node, self.path
            if self._air is None:
                node = BulletCharacterControllerNode(self._standing[0].get_shape(), .27, 'player-air')
                node.set_gravity(0)
                path = self.path.get_parent().attach_new_node(node)
                path.set_collide_mask(_CHARACTERS)
                self._air = node, path
            node, path = self._air
        else:
            # Panda 1.10 exposes no setter/reset for the native vertical velocity.
            # Reuse the shape; reset the controller only at this state transition.
            node = BulletCharacterControllerNode(self._standing[0].get_shape(), .27, 'player')
            node.set_gravity(20)
            path = self.path.get_parent().attach_new_node(node)
            path.set_collide_mask(_CHARACTERS)
        path.set_pos(to_point(anchor))
        if self.active:
            self.world.remove_character(self.node)
            self.world.attach_character(node)
        if not enabled:
            self._standing[1].remove_node()
            self._standing = node, path
        self.node, self.path, self.vertical_override = node, path, enabled

    def jump(self, speed: float) -> bool:
        if not self.node.can_jump():
            return False
        self.node.set_jump_speed(speed)
        self.node.set_max_jump_height(3)
        self.node.do_jump()
        return True

    def set_crouched(self, enabled: bool) -> bool:
        """Swap cached controllers, preserving feet and rejecting blocked standing space."""
        if enabled and self.vertical_override:
            return False
        if self.crouched == enabled:
            return True
        anchor = self.position()
        if self._low is None:
            if self._standing is None:
                self._standing = self.node, self.path
            shape = BulletCapsuleShape(self.radius, self.height / 2 - 2 * self.radius, ZUp)
            node = BulletCharacterControllerNode(shape, .135, 'player-slide')
            node.set_gravity(20)
            path = self.path.get_parent().attach_new_node(node)
            path.set_collide_mask(_CHARACTERS)
            self._low = node, path
            query = BulletGhostNode('standing-clearance')
            query.add_shape(self._standing[0].get_shape())
            self._stand_query = self.path.get_parent().attach_new_node(query)
            self._stand_query.set_collide_mask(_CHARACTERS)
        node, path = self._low if enabled else self._standing
        path.set_pos(to_point(anchor - Vec3(0, 0, self.height / 4 if enabled else 0)))
        if not enabled:
            self._stand_query.set_pos(to_point(anchor))
            query = self._stand_query.node()
            result = self.world.contact_test(query)
            candidates = {contact.get_node1() if contact.get_node0() == query else contact.get_node0()
                          for contact in result.get_contacts()}
            for other in candidates - {self.node}:
                # Resolve each pair independently: aggregate queries reuse manifold data.
                pair = self.world.contact_test_pair(query, other)
                for contact in pair.get_contacts():
                    point = contact.get_manifold_point()
                    normal = point.get_normal_world_on_b().z * (1 if contact.get_node0() == query else -1)
                    support = normal > .5 and point.get_distance() > -.08
                    if point.get_distance() < -.01 and not support:
                        return False
        if self.active:
            self.world.remove_character(self.node)
            self.world.attach_character(node)
        self.node, self.path, self.crouched = node, path, enabled
        return True

    def set_active(self, active: bool) -> None:
        """Retira corpos mortos e reinsere os personagens no respawn."""
        if self.active != active:
            if active:
                self.world.attach_character(self.node)
            else:
                self.world.remove_character(self.node)
            self.active = active


class BulletPhysicsAdapter:
    """Executa um passo Bullet e expõe consultas limitadas ao cenário."""

    def __init__(self, root: NodePath) -> None:
        self._root = root
        self._world = BulletWorld()
        self._world.set_gravity(0, 0, -20)
        self._spheres: dict[float, BulletSphereShape] = {}
        self._statics, self._characters = [], []

    def step(self, dt: float) -> None:
        """Avança exatamente um passo, pois o acumulador vive na aplicação."""
        self._world.do_physics(dt, 0)

    def add_static_box(self, name: str, center: Vec3, size: Vec3, *,
                       camera_collision: bool = True) -> "StaticBody":
        """Registra uma caixa estática com o mesmo tamanho da geometria visual."""
        node = BulletRigidBodyNode(name)
        node.set_python_tag('vigilia_surface', f'{name}@{center.x:.4f},{center.y:.4f},{center.z:.4f}')
        node.add_shape(BulletBoxShape(LVector3f(size.x / 2, size.y / 2, size.z / 2)))
        path = self._root.attach_new_node(node)
        path.set_pos(to_point(center))
        path.set_collide_mask((_WORLD | _CHARACTERS) if camera_collision else _CHARACTERS)
        self._world.attach_rigid_body(node)
        body = StaticBody(node, path, self._world)
        self._statics.append(body)
        return body

    def create_character(self, position: Vec3, radius: float = 0.39,
                         height: float = 1.78) -> CharacterBody:
        """Cria o controlador com cápsula em Z e degrau de 0,27 m."""
        shape = BulletCapsuleShape(radius, height - 2 * radius, ZUp)
        node = BulletCharacterControllerNode(shape, 0.27, "player")
        node.set_gravity(20)
        path = self._root.attach_new_node(node)
        path.set_pos(to_point(position))
        path.set_collide_mask(_CHARACTERS)
        self._world.attach_character(node)
        body = CharacterBody(node, path, self._world, radius=radius, height=height)
        self._characters.append(body)
        return body

    def diagnostic_contacts(self):
        manifolds = self._world.get_manifolds()
        return dict(manifolds=len(manifolds), contacts=sum(m.get_num_manifold_points() for m in manifolds))

    def clear_scene(self, keep):
        for body in self._statics:
            body.set_active(False)
            body.path.remove_node()
        self._statics.clear()
        for body in self._characters:
            if body is not keep:
                body.set_active(False)
                body.path.remove_node()
        self._characters = [keep]

    def raycast(self, origin: Vec3, end: Vec3) -> RayHit | None:
        """Consulta a primeira superfície entre dois pontos."""
        result = self._world.ray_test_closest(to_point(origin), to_point(end), _WORLD)
        if result.has_hit():
            node = result.get_node()
            surface = node.get_python_tag('vigilia_surface') or node.get_name()
            return RayHit(_from_panda(result.get_hit_pos()), _from_panda(result.get_hit_normal()),
                          result.get_hit_fraction() * (end - origin).length(), surface)
        return None

    def sweep_sphere(self, origin: Vec3, end: Vec3, radius: float) -> RayHit | None:
        """Move uma esfera de consulta para proteger o plano próximo da câmera."""
        if radius not in self._spheres:
            self._spheres[radius] = BulletSphereShape(radius)
        result = self._world.sweep_test_closest(
            self._spheres[radius], TransformState.make_pos(to_point(origin)),
            TransformState.make_pos(to_point(end)), _WORLD,
        )
        if result.has_hit():
            return RayHit(_from_panda(result.get_hit_pos()), _from_panda(result.get_hit_normal()),
                          result.get_hit_fraction() * (end - origin).length())
        return None


@dataclass(slots=True)
class StaticBody:
    node: BulletRigidBodyNode
    path: NodePath
    world: BulletWorld
    active: bool = True

    def set_active(self, active: bool) -> None:
        if self.active != active:
            if active:
                self.world.attach_rigid_body(self.node)
            else:
                self.world.remove_rigid_body(self.node)
            self.active = active


class BulletContactVolumes:
    """Volumes de contato Bullet que acompanham os ossos sem empurrar atores."""

    def __init__(self, physics: BulletPhysicsAdapter) -> None:
        self._world = physics._world
        self._nodes: dict[tuple[int, str], tuple[NodePath, float]] = {}
        self._shapes: dict[float, BulletSphereShape] = {}
        self._active: set[tuple[int, str]] = set()
        self._volumes: dict[tuple[int, str], tuple[Vec3, float]] = {}

    def sync(self, volumes: dict[tuple[int, str], tuple[Vec3, float]]) -> None:
        """Atualiza poses e remove volumes fora da janela ativa."""
        self._active = set(volumes)
        self._volumes = volumes
        for key, (center, radius) in volumes.items():
            if radius not in self._shapes:
                self._shapes[radius] = BulletSphereShape(radius)
            if key not in self._nodes:
                ghost = BulletGhostNode(f"{key[0]}-{key[1]}")
                ghost.add_shape(self._shapes[radius])
                self._nodes[key] = (NodePath(ghost), radius)
            node, previous_radius = self._nodes[key]
            if previous_radius != radius:
                node.node().remove_shape(node.node().get_shape(0))
                node.node().add_shape(self._shapes[radius])
                self._nodes[key] = node, radius
            node.set_pos(to_point(center))

    def overlaps(self, source: tuple[int, str], targets: Sequence[tuple[int, str]]) -> bool:
        """Consulta os volumes atuais diretamente, sem atraso de broadphase."""
        if source not in self._active:
            return False
        source_node = self._nodes[source][0].node()
        return any(
            target in self._active and
            self._world.contact_test_pair(source_node, self._nodes[target][0].node()).get_num_contacts() > 0
            for target in targets
        )

    def clear(self):
        for node, _ in self._nodes.values():
            node.remove_node()
        self._nodes.clear()
        self._active.clear()
        self._volumes.clear()

    def raycast(self, origin: Vec3, end: Vec3,
                targets: Sequence[tuple[int, str]]) -> VolumeRayHit | None:
        """Intersecciona o raio com as mesmas esferas sincronizadas dos ossos."""
        delta = end - origin
        length = delta.length()
        if length < 1e-8:
            return None
        direction = delta.normalized()
        closest = None
        for key in targets:
            if key not in self._active:
                continue
            center, radius = self._volumes[key]
            offset = origin - center
            projection = offset.dot(direction)
            discriminant = projection * projection - (offset.dot(offset) - radius * radius)
            if discriminant < 0:
                continue
            if -projection + math.sqrt(discriminant) < 0:
                continue
            distance = max(0.0, -projection - math.sqrt(discriminant))
            if distance <= length and (closest is None or distance < closest.distance):
                closest = VolumeRayHit(key, origin + direction * distance, distance)
        return closest

