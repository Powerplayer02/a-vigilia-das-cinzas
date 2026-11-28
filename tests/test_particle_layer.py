"""Particle ceiling, LOD, mutable native buffers and area effects are real contracts."""
from dataclasses import asdict
import math

import pytest
from panda3d.core import GeomVertexReader,NodePath
from vigilia.core.mathx import Vec3
from vigilia.engine.particles import ParticleEmitter,ParticlePool,MAX_PARTICLES,COMBAT_RESERVE,PRESETS
from vigilia.engine.particle_scene import ParticleScene,AREA_EFFECTS


@pytest.mark.parametrize('capacity',(0,-1,2001))
def test_global_pool_ceiling_is_enforced(capacity):
    with pytest.raises(ValueError):ParticlePool(capacity)


def test_ambient_lod_reserves_room_for_combat_and_never_exceeds_ceiling():
    pool=ParticlePool(MAX_PARTICLES)
    assert pool.spawn_lod('mist',Vec3(),ambient=True,count=3000)==MAX_PARTICLES-COMBAT_RESERVE
    assert pool.spawn_lod('mist',Vec3(),ambient=True,count=30)==0
    assert pool.spawn_lod('sparks',Vec3(),count=300)==COMBAT_RESERVE
    assert pool.active_count==MAX_PARTICLES
    assert not pool.spawn('blood',Vec3())
    assert pool.dropped>0


def test_distance_lod_and_fixture_limit_reduce_incoming_density():
    pool=ParticlePool(MAX_PARTICLES);pool.set_limit(500)
    assert pool.spawn_lod('dust',Vec3(),count=20,distance=18)==10
    assert pool.spawn_lod('dust',Vec3(),count=20,distance=30)==5
    assert pool.spawn_lod('dust',Vec3(),count=20,distance=41)==0
    with pytest.raises(ValueError):pool.set_limit(1)


@pytest.mark.parametrize('area',AREA_EFFECTS)
def test_area_effects_are_deterministic_paused_and_bounded(area):
    one=ParticleEmitter(NodePath('one'),capacity=MAX_PARTICLES)
    two=ParticleEmitter(NodePath('two'),capacity=MAX_PARTICLES)
    directors=[ParticleScene(emitter) for emitter in (one,two)]
    for director in directors:
        director.set_area(area,(Vec3(0,0,0),))
        for _ in range(30):director.update(.1,Vec3(0,0,1));director.emitter.update(.1)
    assert [asdict(p) for p in one.pool.slots]==[asdict(p) for p in two.pool.slots]
    assert 0<one.pool.active_count<MAX_PARTICLES-COMBAT_RESERVE
    before=one.pool._rng.getstate(),directors[0].rng.getstate(),one.pool.active_count
    directors[0].update(1,Vec3(),paused=True)
    assert before==(one.pool._rng.getstate(),directors[0].rng.getstate(),one.pool.active_count)


def test_ring_plane_shape_and_buffers_stay_attached_to_the_live_graph():
    emitter=ParticleEmitter(NodePath('scene'),capacity=MAX_PARTICLES)
    slots=[id(p) for p in emitter.pool.slots]
    emitter.spawn('shockwave',Vec3(10,20,.1));emitter.update(.15)
    geometry=emitter.nodes[1].node().get_geom(0)
    reader=GeomVertexReader(geometry.get_vertex_data(),'vertex')
    points=[tuple(reader.get_data3()) for _ in range(4)]
    assert len({p[2] for p in points})==1
    assert points[0][0]<10<points[2][0]
    data_id=geometry.get_vertex_data().this;geom_id=geometry.this
    for _ in range(3):emitter.update(.01)
    assert emitter.nodes[1].node().get_geom(0).this==geom_id
    assert emitter.data.this==data_id and [id(p) for p in emitter.pool.slots]==slots


def test_new_presets_are_finite_and_all_shapes_are_covered_during_restored_warmup():
    emitter=ParticleEmitter(NodePath('scene'),capacity=MAX_PARTICLES)
    emitter.spawn('souls',Vec3(4,3,2));emitter.update(.1)
    emitter.spawn('level',Vec3(4,3,2));emitter.update(.1,Vec3(4,3,2))
    before=[asdict(p) for p in emitter.pool.slots],emitter.pool._free.copy(),emitter.pool._rng.getstate()
    counters=emitter.pool.requested,emitter.pool.emitted,emitter.pool.dropped
    target=emitter._last_target
    with emitter.warmup():
        assert {p.shape for p in emitter.pool.slots if p.alive}=={0,1,2,3}
        assert all(math.isfinite(p.x+p.y+p.z+p.size) for p in emitter.pool.slots)
        assert emitter.pool.active_count==len(PRESETS)
    assert before==([asdict(p) for p in emitter.pool.slots],emitter.pool._free,emitter.pool._rng.getstate())
    assert counters==(emitter.pool.requested,emitter.pool.emitted,emitter.pool.dropped)
    assert emitter._last_target==target


def test_slam_ring_uses_ground_contact_not_a_body_center_offset():
    from vigilia.core.events import SlamImpactEvent
    from vigilia.game import Game
    game=Game.__new__(Game);effects=[]
    game._sfx=lambda *args:None
    game._emit=lambda preset,position:effects.append((preset,position))
    game._on_slam_effect(SlamImpactEvent(Vec3(3,4,0),2.5,100,30))
    assert effects[0][0]=='shockwave' and effects[0][1].z==pytest.approx(.04)


def test_native_blend_indices_rebuild_after_empty_warmup():
    emitter=ParticleEmitter(NodePath('scene'),capacity=40)
    with emitter.warmup():pass
    emitter.spawn('embers',Vec3(),count=19);emitter.update(0)
    for index in range(19):
        assert emitter.primitives[1].get_vertex(index*6+1)==index*4+1
        assert emitter.primitives[0].get_vertex(index*6+1)==0


def test_conservative_bounds_contain_rotated_billboards_and_ground_rings():
    root=NodePath('scene');camera=root.attach_new_node('camera');camera.set_hpr(32,17,4)
    emitter=ParticleEmitter(root,capacity=40,camera=camera)
    for preset in ('smoke','shockwave','rain','dust'):emitter.spawn(preset,Vec3(8,12,2))
    emitter.update(.2)
    for geometry in emitter.geometries:
        bounds=geometry.get_bounds();reader=GeomVertexReader(geometry.get_vertex_data(),'vertex')
        while not reader.is_at_end():assert bounds.contains(reader.get_data3())


def test_light_clock_freezes_and_resumes_without_hot_root_state_changes():
    from types import SimpleNamespace
    from vigilia.engine.render import ArenaRenderer
    now=[100.]
    renderer=ArenaRenderer.__new__(ArenaRenderer);renderer.root=NodePath('root')
    renderer._app=SimpleNamespace(_clock=SimpleNamespace(get_frame_time=lambda:now[0]))
    renderer._elapsed=0.;renderer._light_offset=None;renderer._light_paused=False;renderer._light_pause_started=0.
    renderer._sync_light_clock(False)
    state=renderer.root.get_state();now[0]=101.
    renderer._sync_light_clock(False)
    assert state==renderer.root.get_state()
    now[0]=101.5;renderer._sync_light_clock(True)
    # get_vector exposes native storage owned by ShaderInput. Keep its owner
    # alive while converting the returned reference to a Python tuple.
    paused_input=renderer.root.get_shader_input('light_clock')
    assert tuple(paused_input.get_vector())[:3]==(100,1.5,1)
    paused=renderer.root.get_state();now[0]=110.5;renderer._sync_light_clock(True)
    assert paused==renderer.root.get_state()
    renderer._sync_light_clock(False)
    resumed_input=renderer.root.get_shader_input('light_clock')
    assert tuple(resumed_input.get_vector())[:3]==(109,0,0)


def test_unused_capacity_does_not_anchor_a_regional_batch_at_world_origin():
    emitter=ParticleEmitter(NodePath('scene'),capacity=MAX_PARTICLES)
    target=Vec3(240,25,1)
    emitter.spawn('embers',target,count=500);emitter.update(0,target)
    assert emitter.root.get_bounds().get_center().x==pytest.approx(240,abs=1e-4)
