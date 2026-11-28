"""Pool visual de quads reutilizados; nenhum contato ou passo de gameplay."""

from dataclasses import dataclass
from dataclasses import replace
from contextlib import contextmanager
import math
import random

import numpy as np
from panda3d.core import (
    ColorBlendAttrib, TransparencyAttrib, Geom, GeomNode, GeomTriangles,
    GeomVertexData, GeomVertexFormat, GeomVertexArrayFormat, InternalName, Shader,
    BoundingBox, Point3,
)
from vigilia.core.mathx import Vec3


MAX_PARTICLES = 2000
COMBAT_RESERVE = 256

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
    "dust": (12, .65, (.47, .42, .35), -.4, False, "drift", .11),
    "smoke": (3, 2.8, (.25, .24, .23), .08, False, "rise", .24),
    "flame": (4, .65, (1., .31, .045), .6, True, "rise", .12),
    "mist": (2, 4., (.42, .53, .49), 0., False, "drift", .85),
    "rain": (8, .7, (.62, .76, .82), -9., False, "rain", .16),
    "splash": (6, .3, (.55, .72, .73), -7., False, "burst", .045),
    "ash": (3, 3., (.65, .61, .53), .05, False, "rise", .04),
    "motes": (3, 5., (.77, .68, .43), 0., True, "drift", .025),
    "debris": (1, 1.2, (.37, .33, .29), -8., False, "fall", .065),
    "shockwave": (1, .38, (1., .54, .18), 0., True, "ring", 2.5),
    "level_wave": (1, .85, (1., .75, .3), 0., True, "ring", 1.6),
}

_SHAPES = {'shockwave':1.,'level_wave':1.,'rain':2.,'sparks':2.,'debris':3.}
_OPACITY = {'smoke':.22,'mist':.10,'dust':.42,'rain':.35,'motes':.45,'ash':.6}

PARTICLE_VERTEX = '''#version 130
uniform mat4 p3d_ModelViewProjectionMatrix;
in vec4 p3d_Vertex;
in vec4 p3d_Color;
in vec3 p3d_MultiTexCoord0;
out vec4 tint;
out vec3 uv_shape;
void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    tint = p3d_Color; uv_shape = p3d_MultiTexCoord0;
}
'''
PARTICLE_FRAGMENT = '''#version 130
in vec4 tint;
in vec3 uv_shape;
out vec4 fragColor;
void main() {
    vec2 q = uv_shape.xy * 2.0 - 1.0;
    float radius = length(q);
    float mask = 1.0 - smoothstep(0.05, 1.0, radius);
    if (uv_shape.z > 0.5 && uv_shape.z < 1.5)
        mask = smoothstep(0.65, 0.8, radius) * (1.0 - smoothstep(0.85, 1.0, radius));
    else if (uv_shape.z > 1.5 && uv_shape.z < 2.5)
        mask = (1.0-smoothstep(0.15,0.85,abs(q.x))) * (1.0-abs(q.y));
    else if (uv_shape.z > 2.5)
        mask = 1.0-smoothstep(0.7,1.0,max(abs(q.x),abs(q.y)));
    fragColor = vec4(tint.rgb, tint.a * mask);
}
'''


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
    shape: float = 0
    opacity: float = 1


class ParticlePool:
    """Admissão atômica: se o preset inteiro não cabe, não rouba partículas vivas."""

    def __init__(self, capacity: int = 500, *, seed: int = 46) -> None:
        if not 1 <= capacity <= MAX_PARTICLES:
            raise ValueError("capacity deve estar entre 1 e 2000")
        self.slots = [Particle() for _ in range(capacity)]
        self._free = list(range(capacity - 1, -1, -1))
        self._rng = random.Random(seed)
        self.limit=capacity
        self.requested=self.emitted=self.dropped=0
        self.blend_revision=0
        self._extent=0

    def set_limit(self,limit):
        """Fixture admission limit; never shrink underneath live particles."""
        if not self.active_count<=limit<=len(self.slots):raise ValueError('Limite inválido')
        self.limit=limit

    @property
    def active_count(self) -> int:
        return len(self.slots) - len(self._free)

    def spawn(self, preset: str, position: Vec3, *, count: int | None = None) -> bool:
        number, lifetime, color, gravity, additive, motion, size = PRESETS[preset]
        number = number if count is None else count
        if number < 0:
            raise ValueError("count negativo")
        self.requested+=number
        if self.active_count+number>self.limit:
            self.dropped+=number
            return False
        self.emitted+=number
        for _ in range(number):
            index=self._free.pop()
            self._extent=max(self._extent,index+1)
            particle = self.slots[index]
            if particle.additive!=additive:self.blend_revision+=1
            particle.alive = True
            particle.x, particle.y, particle.z = position.x, position.y, position.z
            particle.vx = self._rng.uniform(-1.6, 1.6)
            particle.vy = self._rng.uniform(-1.6, 1.6)
            particle.vz = self._rng.uniform(.4, 2.2)
            particle.age, particle.lifetime, particle.gravity = 0., lifetime, gravity
            particle.color, particle.additive, particle.motion, particle.size = color, additive, motion, size
            particle.angle = self._rng.uniform(0, math.tau)
            particle.shape=_SHAPES.get(preset,0.)
            particle.opacity=_OPACITY.get(preset,1.)
            if motion in ('rise','drift'):
                particle.vx*=.12;particle.vy*=.12
                particle.vz=.45 if motion=='rise' else .04
            elif motion in ('rain','fall'):
                particle.vx,particle.vy,particle.vz=.15,0.,-5.
            elif motion=='ring':particle.vx=particle.vy=particle.vz=0.
            if preset == "boss_phase":
                # Emana da superfície, em vez de ficar escondida dentro do torso grande.
                particle.x += math.cos(particle.angle) * .85
                particle.y += math.sin(particle.angle) * .85
                particle.z += self._rng.uniform(-.3, 1.4)
                particle.vx = math.cos(particle.angle) * 2.4
                particle.vy = math.sin(particle.angle) * 2.4
        return True

    def spawn_lod(self,preset,position,*,distance=0.,ambient=False,count=None):
        """Reduce incoming density before exhaustion; reserve space for combat."""
        number=PRESETS[preset][0] if count is None else count
        if number<0:raise ValueError('count negativo')
        density=1. if distance<12 else .5 if distance<24 else .25 if distance<40 else 0.
        ceiling=self.limit-min(COMBAT_RESERVE,self.limit//2) if ambient else self.limit
        admitted=max(0,min(int(math.ceil(number*density)),ceiling-self.active_count))
        # Record both LOD and capacity reductions, including full distance culls.
        self.requested+=number-admitted;self.dropped+=number-admitted
        return admitted if self.spawn(preset,position,count=admitted) else 0

    def update(self, dt: float, target: Vec3 = Vec3()) -> None:
        dt = max(0., dt)
        if dt==0:return
        for index in range(self._extent):
            particle=self.slots[index]
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
        while self._extent and not self.slots[self._extent-1].alive:
            self._extent-=1


class ParticleEmitter:
    """Até 2000 quads em dois lotes; pool, shader e buffers criados no loading."""

    def __init__(self, parent, capacity: int = 500, *, camera=None) -> None:
        self.pool = ParticlePool(capacity)
        self.camera, self.parent = camera, parent
        self.root = parent.attach_new_node("particles")
        self.root.set_light_off()
        self.root.set_shader_off()
        self.root.set_shader(Shader.make(Shader.SL_GLSL,PARTICLE_VERTEX,PARTICLE_FRAGMENT))
        self.root.set_depth_write(False)
        self.root.set_transparency(TransparencyAttrib.M_alpha)
        array = GeomVertexArrayFormat()
        array.add_column(InternalName.get_vertex(), 3, Geom.NT_float32, Geom.C_point)
        array.add_column(InternalName.get_color(), 4, Geom.NT_float32, Geom.C_color)
        array.add_column(InternalName.get_texcoord(),3,Geom.NT_float32,Geom.C_texcoord)
        layout = GeomVertexFormat()
        layout.add_array(array)
        self.data = GeomVertexData("particle-quads", GeomVertexFormat.register_format(layout), Geom.UH_dynamic)
        self.data.set_num_rows(capacity * 4)
        self._vertices = np.zeros((capacity, 4, 10), dtype="float32")
        self._vertices[:,:,7:9]=np.array(((0,0),(1,0),(1,1),(0,1)),dtype='float32')
        self._centers = np.zeros((capacity, 4), dtype="float32")
        self._colors = np.zeros((capacity, 4), dtype="float32")
        self._shapes=np.zeros(capacity,dtype='float32')
        self._center_data=memoryview(self._centers).cast('B').cast('f')
        self._color_data=memoryview(self._colors).cast('B').cast('f')
        self._shape_data=memoryview(self._shapes)
        self._additive = np.zeros(capacity, dtype=bool)
        self._corners = np.array(((-1, -1), (1, -1), (1, 1), (-1, 1)), dtype="float32")
        self._base_indices = np.arange(capacity, dtype="uint32")[:, None] * 4 + np.array((0, 1, 2, 0, 2, 3), dtype="uint32")
        self._indices = [self._base_indices.copy(), self._base_indices.copy()]
        self._vertex_bytes=memoryview(self._vertices).cast('B')
        self._index_bytes=[memoryview(indices).cast('B') for indices in self._indices]
        self._offsets=np.zeros((4,3),dtype='float32')
        self._up_offsets=np.zeros((4,3),dtype='float32')
        self._right=np.zeros(3,dtype='float32');self._up=np.zeros(3,dtype='float32')
        self._batch_mask=np.zeros(capacity,dtype=bool)
        self._dead=np.ones(capacity,dtype=bool)
        self._target_coords=np.zeros(3,dtype='float32')
        self._ring_indices=np.empty(capacity,dtype='int32')
        self._last_blend_revision=-1
        self._bounds_min=np.zeros(3,dtype='float32');self._bounds_max=np.zeros(3,dtype='float32')
        self._bounds=BoundingBox(Point3(0),Point3(0))
        self._bound_start=Point3(0);self._bound_end=Point3(0)
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

    def spawn_lod(self,preset,position,**options):return self.pool.spawn_lod(preset,position,**options)

    def update(self, dt: float, target: Vec3 = Vec3()) -> None:
        self._last_target=target
        self.pool.update(dt, target)
        if self.pool.active_count == 0:
            self._last_blend_revision=-1
            self.root.hide()
            return
        extent=self.pool._extent
        ring_count=0
        self._dead[:extent].fill(True)
        centers,colors=self._center_data,self._color_data
        blend_changed=self._last_blend_revision!=self.pool.blend_revision
        for index in range(extent):
            particle=self.pool.slots[index]
            offset=index*4
            if blend_changed:self._additive[index]=particle.additive
            if not particle.alive:
                colors[offset+3]=0;centers[offset+3]=0
                continue
            self._dead[index]=False
            centers[offset]=particle.x;centers[offset+1]=particle.y;centers[offset+2]=particle.z
            fraction=particle.age/particle.lifetime
            size=particle.size
            if particle.motion=='ring':size*=max(.05,fraction)
            elif particle.motion=='rise':size*=1+fraction*.5
            centers[offset+3]=size
            colors[offset]=particle.color[0];colors[offset+1]=particle.color[1];colors[offset+2]=particle.color[2]
            colors[offset+3]=(1-fraction)*particle.opacity
            if particle.motion=='ring':self._ring_indices[ring_count]=index;ring_count+=1
            self._shape_data[index]=particle.shape
        self.root.show()
        # Degenerate unused quads must follow the active region, not anchor a
        # 2000-slot batch at world origin and defeat culling/depth sorting.
        self._target_coords[:]=(target.x,target.y,target.z)
        np.copyto(self._centers[:extent,:3],self._target_coords,where=self._dead[:extent,None])
        if self.camera is None:
            right, up = (1, 0, 0), (0, 0, 1)
        else:
            orientation = self.camera.get_quat(self.parent)
            right, up = orientation.get_right(), orientation.get_up()
        self._right[:]=right;self._up[:]=up
        np.multiply(self._corners[:,:1],self._right,out=self._offsets)
        np.multiply(self._corners[:,1:],self._up,out=self._up_offsets)
        np.add(self._offsets,self._up_offsets,out=self._offsets)
        np.multiply(self._offsets[None,:,:],self._centers[:extent,None,3:4],out=self._vertices[:extent,:,:3])
        np.add(self._vertices[:extent,:,:3],self._centers[:extent,None,:3],out=self._vertices[:extent,:,:3])
        # Ground rings use the XY plane; other effects billboard toward camera.
        for offset in range(ring_count):
            index=self._ring_indices[offset]
            np.multiply(self._corners,self._centers[index,3],out=self._vertices[index,:,:2])
            np.add(self._vertices[index,:,:2],self._centers[index,:2],out=self._vertices[index,:,:2])
            self._vertices[index,:,2]=self._centers[index,2]
        self._vertices[:extent, :, 3:7] = self._colors[:extent, None, :]
        self._vertices[:extent,:,9]=self._shapes[:extent,None]
        # Retired/unused capacity stays degenerate and transparent. Only the
        # occupied prefix needs billboard/color/shape evaluation.
        self._vertices[extent:,:,:3]=self._target_coords
        self._vertices[extent:,:,3:7]=0
        with memoryview(self.data.modify_array(0)) as buffer:
            buffer.cast('B')[:]=self._vertex_bytes
        if blend_changed:
            for additive, primitive in enumerate(self.primitives):
                indices=self._indices[additive]
                np.copyto(indices,self._base_indices)
                np.not_equal(self._additive,bool(additive),out=self._batch_mask)
                indices[self._batch_mask]=0
                with memoryview(primitive.modify_vertices()) as buffer:
                    buffer.cast('B')[:]=self._index_bytes[additive]
            self._last_blend_revision=self.pool.blend_revision
        # A conservative box from already evaluated centers avoids a second
        # native scan of8000 billboard vertices for each blend batch per frame.
        np.min(self._centers[:extent,:3],axis=0,out=self._bounds_min)
        np.max(self._centers[:extent,:3],axis=0,out=self._bounds_max)
        np.minimum(self._bounds_min,self._target_coords,out=self._bounds_min)
        np.maximum(self._bounds_max,self._target_coords,out=self._bounds_max)
        margin=float(np.max(self._centers[:extent,3]))*math.sqrt(2)
        self._bound_start.set(*(float(value)-margin for value in self._bounds_min))
        self._bound_end.set(*(float(value)+margin for value in self._bounds_max))
        self._bounds.set_min_max(self._bound_start,self._bound_end)
        for geometry,node in zip(self.geometries,self.nodes):
            geometry.set_bounds(self._bounds)
            node.node().mark_internal_bounds_stale()

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
        counters=self.pool.requested,self.pool.emitted,self.pool.dropped
        blend_revision=self.pool.blend_revision
        extent=self.pool._extent
        target=getattr(self,'_last_target',None)
        try:
            self.pool.update(10)
            # All shapes/blend states already exist at boot, including effects
            # first used by late boss phases. No per-preset shader variant/atlas.
            for preset in PRESETS:self.pool.spawn(preset,Vec3(),count=1)
            self.update(0)
            yield
        finally:
            self.pool.slots=slots;self.pool._free=free;self.pool._rng.setstate(rng)
            self.pool.requested,self.pool.emitted,self.pool.dropped=counters
            self.pool.blend_revision=blend_revision
            self.pool._extent=extent
            if target is None:self.update(0)
            else:self.update(0,target)
