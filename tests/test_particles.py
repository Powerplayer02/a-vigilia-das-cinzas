"""Pool e trajetórias visuais independem de um aplicativo Panda3D."""

import ast
from pathlib import Path
import pytest
from panda3d.core import NodePath
from vigilia.core.mathx import Vec3
from vigilia.engine.particles import ParticlePool, ParticleEmitter, PRESETS


@pytest.mark.parametrize("preset,count,lifetime", [("blood", 12, .5), ("embers", 8, .7),
    ("sparks", 8, .3), ("souls", 20, 1), ("level", 30, 2), ("boss_phase", 60, 1.5)])
def test_preset_counts_and_lifetime(preset, count, lifetime):
    pool = ParticlePool()
    assert pool.spawn(preset, Vec3()) and pool.active_count == count
    pool.update(lifetime)
    assert pool.active_count == 0


def test_overflow_is_atomic_and_reuses_same_particle_objects():
    pool = ParticlePool()
    original = [id(slot) for slot in pool.slots]
    assert pool.spawn("blood", Vec3(), count=495)
    assert not pool.spawn("blood", Vec3()) and pool.active_count == 495
    assert pool.spawn("sparks", Vec3(), count=5)
    assert not pool.spawn("sparks", Vec3(), count=1)
    pool.update(1)
    assert pool.spawn("blood", Vec3(), count=500)
    assert [id(slot) for slot in pool.slots] == original


def test_blood_falls_embers_rise_and_negative_dt_does_not_rewind():
    pool = ParticlePool()
    pool.spawn("blood", Vec3(0, 0, 3), count=1)
    particle = pool.slots[0]
    particle.vz = 0
    pool.update(.1)
    assert particle.z < 3
    age = particle.age
    pool.update(-1)
    assert particle.age == age
    pool.spawn("embers", Vec3(), count=1)
    pool.update(.1)
    assert pool.slots[1].z > 0 and pool.slots[1].additive


def test_souls_home_to_current_player_and_level_spirals():
    pool = ParticlePool()
    pool.spawn("souls", Vec3(10, 0), count=1)
    pool.update(.5, Vec3())
    assert pool.slots[0].x == pytest.approx(5)
    pool.update(.25, Vec3(2, 0))
    assert pool.slots[0].x == pytest.approx(3.5)
    pool.spawn("level", Vec3(), count=1)
    pool.update(.1, Vec3(3, 4, 1))
    particle = pool.slots[1]
    assert (particle.x - 3) ** 2 + (particle.y - 4) ** 2 == pytest.approx(.49)
    assert particle.z > 1


def test_emitter_preallocates_500_quads_in_two_batches_without_scene_growth():
    parent = NodePath("root")
    emitter = ParticleEmitter(parent)
    assert emitter.root.get_num_children() == 2
    assert emitter.data.get_num_rows() == 2000
    original_data = emitter.data
    assert emitter.spawn("blood", Vec3())
    emitter.update(0)
    assert not emitter.root.is_hidden() and emitter.pool.active_count == 12
    emitter.update(1)
    assert emitter.root.is_hidden()
    assert emitter.root.get_num_children() == 2 and emitter.data is original_data


def test_fixed_step_unchanged_and_has_no_visual_effect_update():
    import hashlib
    source = (Path(__file__).resolve().parents[1] / "src/vigilia/game.py").read_text(encoding="utf-8")
    method = next(node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.FunctionDef) and node.name == "_fixed_step")
    assert hashlib.sha256(ast.get_source_segment(source, method).encode()).hexdigest() == "568bf0d69b8a81782c627a4fd0c61086c4a817e0c49c03f5dbf809388f5af6bb"


def test_batch_bounds_follow_particles_when_moving_between_areas():
    emitter = ParticleEmitter(NodePath("scene"))
    emitter.spawn("blood", Vec3(0, -8, 1))
    emitter.update(0)
    assert emitter.root.get_bounds().get_center().y < 0
    emitter.clear()
    emitter.spawn("boss_phase", Vec3(0, 27, 2))
    emitter.update(.1)
    assert emitter.root.get_bounds().get_center().y > 10
