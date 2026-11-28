"""Poses procedurais e volumes ligados aos ossos do combate."""

import math
from dataclasses import dataclass
from functools import lru_cache

from vigilia.combat.fighter import Fighter
from vigilia.core.mathx import Transform, Vec3
from vigilia.model.attacks import HitboxKind, AttackDefinition

HURT_BONES = ("head", "torso", "arm_left", "arm_right", "leg_left", "leg_right")
WEAPON_BONES = ("blade_inner", "blade_mid", "blade_tip")


@lru_cache(maxsize=32)
def _rest_pose(size,guarding):
    # Cached local points are immutable Vec3s. Every caller gets fresh mappings;
    # attack overrides and world-space volumes cannot mutate a shared pose.
    grip=Vec3(.35,.09,.11)*size
    tip=Vec3(.35,.24,1.05)*size
    shield=(Vec3(-.10,.58,.20) if guarding else Vec3(-.45,.13,.05))*size
    bones=(('head',Vec3(0,0,.67)*size),('torso',Vec3(0,0,.18)*size),
        ('arm_left',shield*.7),('arm_right',grip),('leg_left',Vec3(-.15,0,-.43)*size),
        ('leg_right',Vec3(.15,0,-.43)*size),('grip',grip),('blade_tip',tip),
        ('blade_mid',grip.lerp(tip,.63)),('blade_inner',grip.lerp(tip,.28)),
        ('shield',shield),('body_center',Vec3()))
    radii=tuple((name,radius*size) for name,radius in (
        ('head',.21),('torso',.32),('arm_left',.18),('arm_right',.18),
        ('leg_left',.22),('leg_right',.22),('shield',.38)))+(('body_center',.05),)
    return bones,radii


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
    size = fighter.body_scale
    points,base_radii=_rest_pose(size,fighter.blocking or fighter.parry_step>=0)
    local=dict(points)
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
        local['arm_right']=local['grip']=grip
        local['blade_tip']=tip
        local['blade_mid']=grip.lerp(tip,.63)
        local['blade_inner']=grip.lerp(tip,.28)
    angle = math.radians(78) if fighter.knockdown_steps else -math.tau * dodge if rolling else 0
    sin_roll, cos_roll = math.sin(angle), math.cos(angle)
    sin_yaw, cos_yaw = math.sin(transform.yaw), math.cos(transform.yaw)
    dip=.22*math.sin(math.pi*dodge)
    origin=transform.position
    bones = {}
    for name, point in local.items():
        y=point.y*cos_roll-point.z*sin_roll
        z=point.y*sin_roll+point.z*cos_roll-dip
        bones[name] = Vec3(
            origin.x+(point.x*cos_yaw+y*sin_yaw),
            origin.y+(-point.x*sin_yaw+y*cos_yaw),origin.z+z,
        )
    radii=dict(base_radii)
    if attack is not None and attack.active and not attack.definition.ranged:
        if attack.definition.hitbox_kind == HitboxKind.CENTER_SPHERE:
            bones["area"] = transform.position
            radii["area"] = sphere_radius(attack.definition, attack.age)
        else:
            radii.update({name: .20 for name in WEAPON_BONES})
    volumes = {name: (bones[name], radius) for name, radius in radii.items()} if fighter.alive else {}
    return CombatPose(bones, volumes)
