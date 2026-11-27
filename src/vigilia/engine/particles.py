"""Pool visual de quads reutilizados; nenhum contato ou passo de gameplay."""

from dataclasses import dataclass
from dataclasses import replace
from contextlib import contextmanager
import math
import random

import numpy as np
from panda3d.core import (
    ColorBlendAttrib, TransparencyAttrib, Geom, GeomNode, GeomTriangles,
    GeomVertexData, GeomVertexFormat, GeomVertexArrayFormat, InternalName,
)
from vigilia.core.mathx import Vec3


# count, lifetime, color, gravity, additive, motion, size
PRESETS = {
    "blood": (12, .5, (.63, .035, .018), -7., False, "burst", .055),
    "embers": (8, .7, (1., .23, .025), 1.3, True, "burst", .065),
    "sparks": (8, .3, (1., .72, .15), -1., True, "burst", .055),
    "souls": (20, 1., (.22, .8, 1.), 0., True, "home", .045),
    "level": (30, 2., (1., .73, .2), 0., True, "spiral", .055),
    "boss_phase": (60, 1.5, (1., .25, .04), 1.4, True, "burst", .085),
    "arcane": (8, .5, (.25, .6, 1.), .4, True, "burst", .06),
    "healing": (15, 1., (1., .8, .35), 0., True, "spiral", .05),
}


@dataclass(slots=True)
class Particle:
    alive: bool = False
    x: float = 0
    y: float = 0
    z: float = 0
    vx: float = 0
    vy: float = 0
    vz: float = 0
    age: float = 0
    lifetime: float = 1
    gravity: float = 0
    color: tuple = (1, 1, 1)
    additive: bool = False
    motion: str = "burst"
    size: float = .05
    angle: float = 0


class ParticlePool:
    """Admissão atômica: se o preset inteiro não cabe, não rouba partículas vivas."""

    def __init__(self, capacity: int = 500, *, seed: int = 46) -> None:
        if capacity < 1:
            raise ValueError("capacity deve ser positiva")
        self.slots = [Particle() for _ in range(capacity)]
        self._free = list(range(capacity - 1, -1, -1))
        self._rng = random.Random(seed)

    @property
    def active_count(self) -> int:
        return len(self.slots) - len(self._free)

    def spawn(self, preset: str, position: Vec3, *, count: int | None = None) -> bool:
        number, lifetime, color, gravity, additive, motion, size = PRESETS[preset]
        number = number if count is None else count
        if number < 0:
            raise ValueError("count negativo")
        if len(self._free) < number:
            return False
        for _ in range(number):
            particle = self.slots[self._free.pop()]
            particle.alive = True
            particle.x, particle.y, particle.z = position.x, position.y, position.z
            particle.vx = self._rng.uniform(-1.6, 1.6)
            particle.vy = self._rng.uniform(-1.6, 1.6)
            particle.vz = self._rng.uniform(.4, 2.2)
            particle.age, particle.lifetime, particle.gravity = 0., lifetime, gravity
            particle.color, particle.additive, particle.motion, particle.size = color, additive, motion, size
            particle.angle = self._rng.uniform(0, math.tau)
            if preset == "boss_phase":
                # Emana da superfície, em vez de ficar escondida dentro do torso grande.
                particle.x += math.cos(particle.angle) * .85
                particle.y += math.sin(particle.angle) * .85
                particle.z += self._rng.uniform(-.3, 1.4)
                particle.vx = math.cos(particle.angle) * 2.4
                particle.vy = math.sin(particle.angle) * 2.4
        return True

    def update(self, dt: float, target: Vec3 = Vec3()) -> None:
        dt = max(0., dt)
        for index, particle in enumerate(self.slots):
            if not particle.alive:
                continue
            particle.age += dt
            if particle.age >= particle.lifetime:
                particle.alive = False
                self._free.append(index)
                continue
            if particle.motion == "home":
                # Fração restante garante chegada mesmo com dt variável.
                fraction = min(1., dt / max(dt, particle.lifetime - particle.age + dt))
                particle.x += (target.x - particle.x) * fraction
                particle.y += (target.y - particle.y) * fraction
                particle.z += (target.z + .7 - particle.z) * fraction
            elif particle.motion == "spiral":
                angle = particle.angle + particle.age * 5
                particle.x = target.x + math.cos(angle) * .7
                particle.y = target.y + math.sin(angle) * .7
                particle.z = target.z + .2 + particle.age * .9
            else:
                particle.vz += particle.gravity * dt
                particle.x += particle.vx * dt
                particle.y += particle.vy * dt
                particle.z += particle.vz * dt


class ParticleEmitter:
    """500 quads em dois lotes: um normal, outro aditivo; buffers reutilizados."""

    def __init__(self, parent, capacity: int = 500, *, camera=None) -> None:
        self.pool = ParticlePool(capacity)
        self.camera, self.parent = camera, parent
        self.root = parent.attach_new_node("particles")
        self.root.set_light_off()
        self.root.set_shader_off()
        self.root.set_depth_write(False)
        self.root.set_transparency(TransparencyAttrib.M_alpha)
        array = GeomVertexArrayFormat()
        array.add_column(InternalName.get_vertex(), 3, Geom.NT_float32, Geom.C_point)
        array.add_column(InternalName.get_color(), 4, Geom.NT_float32, Geom.C_color)
        layout = GeomVertexFormat()
        layout.add_array(array)
        self.data = GeomVertexData("particle-quads", GeomVertexFormat.register_format(layout), Geom.UH_dynamic)
        self.data.set_num_rows(capacity * 4)
        self._vertices = np.zeros((capacity, 4, 7), dtype="float32")
        self._centers = np.zeros((capacity, 4), dtype="float32")
        self._colors = np.zeros((capacity, 4), dtype="float32")
        self._additive = np.zeros(capacity, dtype=bool)
        self._corners = np.array(((-1, -1), (1, -1), (1, 1), (-1, 1)), dtype="float32")
        self._base_indices = np.arange(capacity, dtype="uint32")[:, None] * 4 + np.array((0, 1, 2, 0, 2, 3), dtype="uint32")
        self._indices = [self._base_indices.copy(), self._base_indices.copy()]
        self.primitives, self.nodes, self.geometries = [], [], []
        for additive in (False, True):
            primitive = GeomTriangles(Geom.UH_dynamic)
            primitive.set_index_type(Geom.NT_uint32)
            for first in range(0, capacity * 4, 4):
                primitive.add_vertices(first, first + 1, first + 2)
                primitive.add_vertices(first, first + 2, first + 3)
            geometry = Geom(self.data)
            geometry.add_primitive(primitive)
            self.geometries.append(geometry)
            geometry_node = GeomNode("additive" if additive else "alpha")
            geometry_node.add_geom(geometry)
            node = self.root.attach_new_node(geometry_node)
            if additive:
                node.set_attrib(ColorBlendAttrib.make(ColorBlendAttrib.M_add,
                    ColorBlendAttrib.O_incoming_alpha, ColorBlendAttrib.O_one))
            self.primitives.append(primitive)
            self.nodes.append(node)
        self.update(0)

    def spawn(self, preset: str, position: Vec3, *, count: int | None = None) -> bool:
        return self.pool.spawn(preset, position, count=count)

    def update(self, dt: float, target: Vec3 = Vec3()) -> None:
        self.pool.update(dt, target)
        for index, particle in enumerate(self.pool.slots):
            if not particle.alive:
                self._colors[index, 3] = 0
                self._centers[index, 3] = 0
                continue
            self._centers[index] = (particle.x, particle.y, particle.z, particle.size)
            self._colors[index] = (*particle.color, 1 - particle.age / particle.lifetime)
            self._additive[index] = particle.additive
        if self.pool.active_count == 0:
            self.root.hide()
            return
        self.root.show()
        if self.camera is None:
            right, up = (1, 0, 0), (0, 0, 1)
        else:
            orientation = self.camera.get_quat(self.parent)
            right, up = orientation.get_right(), orientation.get_up()
        offsets = self._corners[:, :1] * np.asarray(right) + self._corners[:, 1:] * np.asarray(up)
        self._vertices[:, :, :3] = self._centers[:, None, :3] + offsets[None, :, :] * self._centers[:, None, 3:4]
        self._vertices[:, :, 3:] = self._colors[:, None, :]
        self.data.modify_array(0).modify_handle().set_data(self._vertices.tobytes())
        for additive, primitive in enumerate(self.primitives):
            indices = self._indices[additive]
            np.copyto(indices, self._base_indices)
            indices[self._additive != bool(additive)] = 0
            primitive.modify_vertices().modify_handle().set_data(indices.tobytes())
            # Escrita pelo handle não notifica os limites do grafo automaticamente.
            self.geometries[additive].mark_bounds_stale()
            self.nodes[additive].node().mark_internal_bounds_stale()

    def clear(self):
        self.pool.update(10)
        self.update(0)

    @contextmanager
    def warmup(self):
        """Expose both existing particle draw states during loading, then restore.

        Preserves particles, free-list order and visual RNG. No new preset mesh
        is built: phase effects reuse these same alpha/additive buffers.
        """
        slots=[replace(slot) for slot in self.pool.slots]
        free=self.pool._free.copy();rng=self.pool._rng.getstate()
        try:
            self.pool.update(10)
            self.pool.spawn('boss_phase',Vec3(),count=min(12,len(slots)//2))
            self.pool.spawn('blood',Vec3(),count=min(12,len(slots)//2))
            self.update(0)
            yield
        finally:
            self.pool.slots=slots;self.pool._free=free;self.pool._rng.setstate(rng)
            self.update(0)
