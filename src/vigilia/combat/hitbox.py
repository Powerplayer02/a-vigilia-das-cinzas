"""Poses procedurais e volumes ligados aos ossos do combate."""

import math
from dataclasses import dataclass

from vigilia.combat.fighter import Fighter
from vigilia.core.mathx import Transform, Vec3
from vigilia.model.attacks import HitboxKind, AttackDefinition

HURT_BONES = ("head", "torso", "arm_left", "arm_right", "leg_left", "leg_right")
WEAPON_BONES = ("blade_inner", "blade_mid", "blade_tip")


def sphere_radius(definition: AttackDefinition, age: int) -> float:
    progress = max(0.0, min(1.0, (age - definition.windup) / max(1, definition.active - 1)))
    return definition.sphere_radius_start + progress * (definition.sphere_radius_end - definition.sphere_radius_start)


@dataclass(frozen=True, slots=True)
class CombatPose:
    """Pontos de ossos mundiais compartilhados com a apresentação."""

    bones: dict[str, Vec3]
    volumes: dict[str, tuple[Vec3, float]]


def evaluate_pose(transform: Transform, fighter: Fighter, *, dodge: float = 0,
                  rolling: bool = False) -> CombatPose:
    """Avalia a pose do passo corrente antes de qualquer consulta de contato."""
    local = {
        "head": Vec3(0, 0, .67), "torso": Vec3(0, 0, .18),
        "arm_left": Vec3(-.35, 0, .15), "arm_right": Vec3(.35, 0, .15),
        "leg_left": Vec3(-.15, 0, -.43), "leg_right": Vec3(.15, 0, -.43),
    }
    size = fighter.body_scale
    local = {name: point * size for name, point in local.items()}
    grip = Vec3(.35, .09, .11) * size
    tip = Vec3(.35, .24, 1.05) * size
    attack = fighter.attack
    if attack is not None:
        definition = attack.definition
        progress = (attack.age - definition.windup) / max(1, definition.active - 1)
        progress = max(0.0, min(1.0, progress))
        angle = -definition.arc / 2 + progress * definition.arc
        grip = Vec3(math.sin(angle) * .38, math.cos(angle) * .43, .22) * size
        tip = Vec3(math.sin(angle) * definition.reach,
                   math.cos(angle) * definition.reach, .25 * size - max(0, size - 1) * 1.1)
        if definition.ranged:
            grip, tip = Vec3(.22, .25, .25), Vec3(.22, 1.0, .25)
        elif definition.hitbox_kind == HitboxKind.CENTER_SPHERE:
            tip = Vec3(0, .8, -.8 * size)
    guarding = fighter.blocking or fighter.parry_step >= 0
    shield = Vec3(-.10, .58, .20) if guarding else Vec3(-.45, .13, .05)
    shield = shield * size
    local["arm_right"] = grip
    local["arm_left"] = shield * .7
    local["grip"] = grip
    local["blade_tip"] = tip
    local["blade_mid"] = grip.lerp(tip, .63)
    local["blade_inner"] = grip.lerp(tip, .28)
    local["shield"] = shield
    local["body_center"] = Vec3()
    angle = math.radians(78) if fighter.knockdown_steps else -math.tau * dodge if rolling else 0
    sin_roll, cos_roll = math.sin(angle), math.cos(angle)
    sin_yaw, cos_yaw = math.sin(transform.yaw), math.cos(transform.yaw)
    bones = {}
    for name, point in local.items():
        point = Vec3(point.x, point.y * cos_roll - point.z * sin_roll,
                     point.y * sin_roll + point.z * cos_roll - .22 * math.sin(math.pi * dodge))
        bones[name] = transform.position + Vec3(
            point.x * cos_yaw + point.y * sin_yaw,
            -point.x * sin_yaw + point.y * cos_yaw, point.z,
        )
    radii = {"head": .21, "torso": .32, "arm_left": .18, "arm_right": .18,
             "leg_left": .22, "leg_right": .22, "shield": .38}
    radii = {name: radius * size for name, radius in radii.items()}
    radii["body_center"] = .05
    if attack is not None and attack.active and not attack.definition.ranged:
        if attack.definition.hitbox_kind == HitboxKind.CENTER_SPHERE:
            bones["area"] = transform.position
            radii["area"] = sphere_radius(attack.definition, attack.age)
        else:
            radii.update({name: .20 for name in WEAPON_BONES})
    volumes = {name: (bones[name], radius) for name, radius in radii.items()} if fighter.alive else {}
    return CombatPose(bones, volumes)
