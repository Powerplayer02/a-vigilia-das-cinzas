"""Exercita colisão Bullet e câmera sem abrir uma janela."""

from panda3d.core import NodePath

from vigilia.core.mathx import Vec3
from vigilia.core.timing import FIXED_DT
from vigilia.engine.camera import SpringArmCamera
from vigilia.engine.physics import BulletPhysicsAdapter, BulletContactVolumes


def test_capsule_stands_on_floor_and_stops_at_wall() -> None:
    world = BulletPhysicsAdapter(NodePath("physics"))
    world.add_static_box("floor", Vec3(0, 0, -.5), Vec3(16, 16, 1))
    world.add_static_box("wall", Vec3(0, 2, 1), Vec3(8, .5, 2))
    character = world.create_character(Vec3(0, 0, 1))
    character.set_velocity(Vec3(0, 6, 0))
    for _ in range(90):
        world.step(FIXED_DT)
    assert 0.75 < character.position().z < 1.05
    assert 1.0 < character.position().y < 1.65
    assert world.raycast(Vec3(0, 0, 1), Vec3(0, 3, 1)) is not None


def test_spring_arm_ignores_character_and_retracts_at_wall() -> None:
    world = BulletPhysicsAdapter(NodePath("physics"))
    player = Vec3(0, 0, 1)
    world.create_character(player)
    camera = SpringArmCamera(world, .003)
    assert camera.update(player, FIXED_DT).position.y < -5
    world.add_static_box("wall", Vec3(0, -2, 2), Vec3(8, .5, 4))
    assert -1.75 < camera.update(player, FIXED_DT).position.y < -1


def test_bone_contacts_follow_pose_immediately_and_disable_between_swings() -> None:
    physics = BulletPhysicsAdapter(NodePath("physics"))
    volumes = BulletContactVolumes(physics)
    source, target = (1, "blade_tip"), (2, "torso")
    volumes.sync({source: (Vec3(), .2), target: (Vec3(.3, 0), .25)})
    assert volumes.overlaps(source, (target,))
    volumes.sync({source: (Vec3(-2, 0), .2), target: (Vec3(.3, 0), .25)})
    assert not volumes.overlaps(source, (target,))
    volumes.sync({source: (Vec3(), .2), target: (Vec3(.3, 0), .25)})
    assert volumes.overlaps(source, (target,))
    volumes.sync({target: (Vec3(.3, 0), .25)})
    assert not volumes.overlaps(source, (target,))


def test_hitscan_intersects_current_bone_spheres_only_in_front() -> None:
    physics = BulletPhysicsAdapter(NodePath("physics"))
    volumes = BulletContactVolumes(physics)
    volumes.sync({(1, "torso"): (Vec3(0, 3, 1), .3),
                  (2, "torso"): (Vec3(0, -2, 1), .3)})
    hit = volumes.raycast(Vec3(0, 0, 1), Vec3(0, 8, 1), ((1, "torso"), (2, "torso")))
    assert hit is not None and hit.target == (1, "torso")
    assert abs(hit.distance - 2.7) < 1e-6
