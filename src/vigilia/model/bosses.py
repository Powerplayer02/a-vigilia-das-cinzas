"""Perfil numérico do chefe carregado do TOML pelo bootstrap."""

from dataclasses import dataclass, fields
from pathlib import Path
import math
import tomllib

from vigilia.model.attacks import AttackDefinition, AttackKind, DamagePacket, HitboxKind
from vigilia.model.items import WeaponSpec, ScalingGrades, WEAPONS
from vigilia.model.stats import StatsBlock


@dataclass(frozen=True, slots=True)
class BossProfile:
    id: str
    name: str
    arena: str
    max_hp: int
    poise: int
    souls: int
    intro_steps: int
    death_steps: int
    transition_steps: int
    phase2_threshold: float
    aggression_phase1: float
    aggression_phase2: float
    punish_cooldown: int
    grab_cooldown: int
    aoe_cooldown: int
    guard_trigger_steps: int
    close_trigger_steps: int
    reposition_steps: int
    weapon: WeaponSpec
    bounds: tuple[float, ...] = (-10, 14.5, 10, 36)
    music_prefix: str = "boss"
    reward_item: str = ""
    phase3_threshold: float = 0.

    @property
    def stats(self) -> StatsBlock:
        return StatsBlock(vigor=(self.max_hp - 80) // 6, endurance=(self.poise - 20) // 2)

    def moveset(self, phase: int) -> tuple[AttackDefinition, ...]:
        return self.weapon.attacks if phase >= 2 else self.weapon.attacks[:3]


def load_boss_profile(path: Path, *, register: bool = True) -> BossProfile:
    """Lê e registra o catálogo usado por combate e persistência."""
    with path.open("rb") as file:
        data = tomllib.load(file)
    if data["id"] not in ("warden_of_the_forge", "abbess_of_the_tide", "last_ember_custodian"):
        raise ValueError("Identificador de chefe desconhecido.")
    if "bounds" in data:
        data["bounds"] = tuple(data["bounds"])
        bounds = data["bounds"]
        if len(bounds) != 4 or not all(math.isfinite(value) for value in bounds) or not (bounds[0] < bounds[2] and bounds[1] < bounds[3]):
            raise ValueError("Limites de arena inválidos.")
    moves = []
    for move in data.pop("moves"):
        moves.append(AttackDefinition(
            AttackKind(move["id"]), move["windup"], move["active"], move["recovery"], 0,
            DamagePacket(physical_slash=move.get("slash", 0), physical_strike=move.get("strike", 0),
                         physical_pierce=move.get("pierce", 0), fire=move.get("fire", 0),
                         magic=move.get("magic", 0), holy=move.get("holy", 0), poise=move["poise"]),
            move["reach"], move["arc"], cancel_from=move.get("cancel_from"),
            parryable=move.get("parryable", True), hitbox_kind=HitboxKind(move.get("hitbox_kind", "bone_sphere")),
            sphere_radius_start=move.get("sphere_radius_start", 0),
            sphere_radius_end=move.get("sphere_radius_end", 0), blockable=move.get("blockable", True),
            block_damage_fraction=move.get("block_damage_fraction", .22),
            knockdown_steps=move.get("knockdown_steps", 0),
            ranged=move.get("ranged", False),
        ))
    if len(moves) != 5:
        raise ValueError("O Vigia precisa dos cinco movimentos do perfil.")
    weapon_id = "forge_warden_weapon" if data["id"] == "warden_of_the_forge" else "tide_crosier"
    if data["id"] == "last_ember_custodian":
        weapon_id = "custodian_brand"
    weapon_name = {"forge_warden_weapon": "Martelo da Fornalha", "tide_crosier": "Báculo das Marés", "custodian_brand": "Marca da última chama"}[weapon_id]
    weapon = WeaponSpec(weapon_id, weapon_name, moves[0].packet, ScalingGrades(),
                        StatsBlock(0, 0, 0, 0, 0, 0, 0), (0,), "forge_warden", 12, tuple(moves))
    profile = BossProfile(**data, weapon=weapon)
    if profile.stats.max_hp != profile.max_hp or profile.stats.max_poise != profile.poise:
        raise ValueError("HP e poise do perfil precisam corresponder às curvas de atributos.")
    expected = (AttackKind.SLOW_OVERHEAD, AttackKind.WIDE_SWEEP, AttackKind.BACKSTEP_PUNISH,
                AttackKind.FORGE_GRAB, AttackKind.FIRE_AOE_RING)
    if profile.id == "abbess_of_the_tide":
        expected = (AttackKind.TIDE_STRIKE, AttackKind.TIDE_SWEEP, AttackKind.TIDE_BOLT, AttackKind.TIDE_GRASP, AttackKind.TIDE_NOVA)
    timers = (profile.intro_steps, profile.death_steps, profile.transition_steps, profile.punish_cooldown,
              profile.grab_cooldown, profile.aoe_cooldown, profile.guard_trigger_steps,
              profile.close_trigger_steps, profile.reposition_steps)
    if tuple(move.kind for move in moves) != expected or any(type(value) is not int or value < 1 for value in timers):
        raise ValueError("Perfil de chefe incompleto.")
    if (not 0 < profile.phase2_threshold < 1 or profile.souls < 0 or
            not all(0 <= value <= 1 for value in (profile.aggression_phase1, profile.aggression_phase2))):
        raise ValueError("Limiares ou recompensa do chefe inválidos.")
    if profile.phase3_threshold and not 0 < profile.phase3_threshold < profile.phase2_threshold:
        raise ValueError("Terceira fase inválida.")
    for move in moves:
        if (any(type(value) is not int or value < 1 for value in (move.windup, move.active, move.recovery)) or
                not all(math.isfinite(value) and value >= 0 for value in
                        (move.reach, move.arc, move.sphere_radius_start, move.sphere_radius_end,
                         *(getattr(move.packet, field.name) for field in fields(DamagePacket)))) or
                not 0 <= move.block_damage_fraction <= 1 or
                type(move.knockdown_steps) is not int or move.knockdown_steps < 0 or
                type(move.blockable) is not bool or type(move.parryable) is not bool or
                move.sphere_radius_start > move.sphere_radius_end or
                (move.hitbox_kind == HitboxKind.CENTER_SPHERE and move.sphere_radius_end <= 0) or
                (move.cancel_from is not None and (type(move.cancel_from) is not int or
                    not 0 <= move.cancel_from < move.duration))):
            raise ValueError("Ataque do chefe inválido.")
    if register:
        WEAPONS[weapon.id] = weapon
    return profile
