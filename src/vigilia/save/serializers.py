"""JSON canônico e validação dos contratos públicos de snapshot."""

import json
import math
from dataclasses import asdict, replace
from pathlib import Path
from vigilia.model import enemies as _enemy_catalog
from vigilia.model.areas import AREA_BOUNDS

from vigilia.core.mathx import Vec3
from vigilia.core.timing import TIMING_VERSION, PARRY_RECOVERY_STEPS, CHARGE_STEPS
from vigilia.model.attacks import AttackDefinition, AttackKind, DamagePacket, StatusEffect, HitboxKind
from vigilia.model.inventory import Inventory
from vigilia.model.items import WEAPONS, ITEM_WEIGHTS, GEAR_IDS
from vigilia.model.spells import SPELLS
from vigilia.model.snapshots import (
    SNAPSHOT_VERSION, ActorSnapshot, AttackSnapshot, ControlSnapshot, FighterSnapshot,
    MotionSnapshot, PlayerSnapshot, SaveSnapshot, WorldSnapshot, BossSnapshot, AreaSnapshot,
)
from vigilia.model.stats import StatsBlock, ResistBlock
from vigilia.model.characters import CHARACTER_CLASSES, validate_name


class SaveFormatError(ValueError):
    """Snapshot inválido ou criado com contratos incompatíveis."""


def _fighter(data: dict) -> FighterSnapshot:
    data = data.copy()
    boss_weapons = {"custodian_brand": "custodian.toml", "tide_crosier": "tide.toml", "forge_warden_weapon": "warden.toml"}
    if data["weapon_id"] in boss_weapons and data["weapon_id"] not in WEAPONS:
        from vigilia.model.bosses import load_boss_profile
        load_boss_profile(Path(__file__).resolve().parents[3] / "data/bosses" / boss_weapons[data["weapon_id"]])
    data["stats"] = StatsBlock(**data["stats"])
    data["resist"] = ResistBlock(**data["resist"])
    if data["attack"] is not None:
        attack = data["attack"].copy()
        definition = attack["definition"].copy()
        definition["kind"] = AttackKind(definition["kind"])
        definition["hitbox_kind"] = HitboxKind(definition.get("hitbox_kind", "bone_sphere"))
        definition["packet"] = DamagePacket(**definition["packet"])
        if definition["status"] is not None:
            effect, amount = definition["status"]
            definition["status"] = (StatusEffect(effect), amount)
        attack["definition"] = AttackDefinition(**definition)
        attack["hit_targets"] = tuple(attack["hit_targets"])
        if attack.get("aim") is not None:
            attack["aim"] = Vec3(**attack["aim"])
        data["attack"] = AttackSnapshot(**attack)
    return FighterSnapshot(**data)


def decode(version: int, timing_version: int, player_json: str, world_json: str) -> SaveSnapshot:
    """Converte e valida todos os dados antes de modificar qualquer ator vivo."""
    try:
        player = json.loads(player_json)
        motion = player["motion"].copy()
        for field in ("position", "velocity", "dodge_direction"):
            motion[field] = Vec3(**motion[field])
        player["motion"] = MotionSnapshot(**motion)
        player["fighter"] = _fighter(player["fighter"])
        player["controls"] = ControlSnapshot(**player["controls"])
        if player["bloodstain_position"] is not None:
            player["bloodstain_position"] = Vec3(**player["bloodstain_position"])
        player["equipped_gear"] = tuple(player["equipped_gear"])
        world = json.loads(world_json)
        def decode_boss(raw):
            data = raw.copy()
            data["position"] = Vec3(**data["position"])
            data["fighter"] = _fighter(data["fighter"]) if data["fighter"] is not None else None
            return BossSnapshot(**data)
        def decode_actors(rows):
            return tuple(ActorSnapshot(row["key"], Vec3(**row["position"]), row["yaw"], _fighter(row["fighter"])) for row in rows)
        world["dormant_areas"] = {key: AreaSnapshot(decode_actors(data["actors"]), tuple(decode_boss(raw) for raw in data["bosses"]))
            for key, data in world.get("dormant_areas", {}).items()}
        bosses = []
        for raw in world.get("bosses", ()):

            data = raw.copy()
            data["position"] = Vec3(**data["position"])
            data["fighter"] = _fighter(data["fighter"]) if data["fighter"] is not None else None
            bosses.append(BossSnapshot(**data))
        world["bosses"] = tuple(bosses)
        world["actors"] = tuple(ActorSnapshot(
            actor["key"], Vec3(**actor["position"]), actor["yaw"], _fighter(actor["fighter"]),
        ) for actor in world["actors"])
        for name in ("discovered_areas", "visited_bonfires", "dead_common", "defeated_bosses",
                     "opened_shortcuts", "collected_items"):
            world[name] = tuple(world[name])
        snapshot = SaveSnapshot(version, timing_version, PlayerSnapshot(**player), WorldSnapshot(**world))
        validate(snapshot)
        return snapshot
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as exc:
        raise SaveFormatError(f"Save inválido: {exc}") from exc


def encode(snapshot: SaveSnapshot) -> tuple[str, str]:
    """Serializa cópias de dados públicos em uma ordem estável."""
    validate(snapshot)
    options = {"ensure_ascii": False, "sort_keys": True, "separators": (",", ":"), "allow_nan": False}
    return json.dumps(asdict(snapshot.player), **options), json.dumps(asdict(snapshot.world), **options)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SaveFormatError(message)


def _integer(value: int, low: int = 0) -> bool:
    return type(value) is int and value >= low


def _finite(*values: float) -> bool:
    return all(type(value) in (int, float) and math.isfinite(value) for value in values)


def _vector(value: Vec3) -> bool:
    return _finite(value.x, value.y, value.z)


def validate(snapshot: SaveSnapshot) -> None:
    """Rejeita versões, referências, recursos e timers inconsistentes."""
    _require(snapshot.version == SNAPSHOT_VERSION, "Versão de snapshot incompatível.")
    _require(snapshot.timing_version == TIMING_VERSION, "Versão de timings incompatível.")
    player, world = snapshot.player, snapshot.world
    _require(validate_name(player.character_name) == player.character_name and
             player.character_class in CHARACTER_CLASSES and _finite(player.playtime_sec) and player.playtime_sec >= 0,
             "Perfil de personagem inválido.")
    allocation = player.starting_allocation
    _require(isinstance(allocation, dict) and set(allocation) <= set(asdict(player.fighter.stats)) and
             all(_integer(value) for value in allocation.values()) and (not allocation or sum(allocation.values()) == 10),
             "Distribuição inicial inválida.")
    scenes = {"patio_da_vigilia", "catedral_submersa", "pantano_das_cinzas", "ruinas_subterraneas", "forno_da_vigilia"}
    _require(world.area_id in scenes and isinstance(world.dormant_areas, dict) and
        set(world.dormant_areas) <= scenes - {world.area_id}, "Regiões persistidas inválidas.")
    areas = (AreaSnapshot(world.actors, world.bosses), *world.dormant_areas.values())
    actors = tuple(actor for area in areas for actor in area.actors)
    bosses = tuple(boss for area in areas for boss in area.bosses)
    keys = {"player"} | {actor.key for actor in actors} | {boss.id for boss in bosses}
    _require(len(keys) == len(actors) + len(bosses) + 1, "Identificadores duplicados.")
    for actor in actors:
        _require(isinstance(actor.key, str) and _vector(actor.position) and _finite(actor.yaw), "Ator inválido.")
    for flags in (world.discovered_areas, world.visited_bonfires, world.dead_common,
                  world.defeated_bosses, world.opened_shortcuts, world.collected_items):
        _require(all(isinstance(key, str) for key in flags) and len(flags) == len(set(flags)), "Flags inválidas.")
    _require(world.last_bonfire in world.visited_bonfires, "Checkpoint não descoberto.")
    _require(set(world.dead_common) <= keys - {"player"}, "Inimigo morto desconhecido.")
    _require(_integer(world.practice_wait) and _integer(world.respawn_remaining), "Timer de mundo inválido.")
    _require((player.fighter.hp == 0) == (world.respawn_remaining > 0), "Estado de respawn divergente.")
    _require(_integer(player.level, 1) and _integer(player.souls), "Progressão inválida.")
    _require(_integer(player.bloodstain_souls) and
             ((player.bloodstain_position is None and player.bloodstain_souls == 0) or
              (player.bloodstain_position is not None and _vector(player.bloodstain_position)
               and player.bloodstain_souls > 0)), "Mancha de sangue inválida.")
    _require(all(key in WEAPONS or key in ITEM_WEIGHTS for key in player.items), "Item desconhecido.")
    _require(all(_integer(count) for count in player.items.values()), "Quantidade de item inválida.")
    for key, level in player.upgrades.items():
        _require(key in WEAPONS and player.items.get(key, 0) > 0 and
                 _integer(level) and level in WEAPONS[key].upgrade_levels, "Melhoria inválida.")
    _require(len(set(player.equipped_gear)) == len(player.equipped_gear) and
             all(key in GEAR_IDS and player.items.get(key, 0) for key in player.equipped_gear),
             "Equipamento inválido.")
    inventory = Inventory(player.items.copy(), player.upgrades.copy(),
                          player.equipped_weapon, player.equipped_gear)
    weapon = inventory.equip(player.equipped_weapon, player.fighter.stats)
    if player.fighter.attack is not None:
        for key, spell in SPELLS.items():
            _require(player.fighter.attack.definition.kind != spell.attack.kind or key in inventory.spells,
                     "Magia não aprendida.")
    _require((weapon.spec_id, weapon.upgrade) == (player.fighter.weapon_id, player.fighter.upgrade),
             "Arma e inventário divergentes.")
    motion = player.motion
    _require(motion.state in ("idle", "walking", "running", "rolling", "backstep", "hit_react", "death", "knockdown"),
             "Estado de locomoção inválido.")
    _require(_vector(motion.position) and _vector(motion.velocity) and _vector(motion.dodge_direction)
             and _finite(motion.yaw, motion.dodge_speed, motion.dodge_progress), "Pose inválida.")
    _require(_integer(motion.dodge_total, 1) and _integer(motion.dodge_remaining) and
             motion.dodge_remaining <= motion.dodge_total and 0 <= motion.dodge_progress <= 1
             and motion.dodge_speed > 0, "Timer de esquiva inválido.")
    _require(motion.dodge_remaining == 0 or motion.state in ("rolling", "backstep"),
             "Ação de esquiva divergente.")
    _require(_integer(player.controls.charge) and player.controls.charge <= CHARGE_STEPS and
             type(player.controls.combo_buffered) is bool, "Buffer de comando inválido.")
    active_keys = {"player"} | {actor.key for actor in world.actors} | {boss.id for boss in world.bosses}
    _validate_fighter(player.fighter, active_keys)
    for area in areas:
        local_keys = {"player"} | {actor.key for actor in area.actors} | {boss.id for boss in area.bosses}
        for actor in area.actors:
            _validate_fighter(actor.fighter, local_keys)
    for actor in actors:
        _require((actor.fighter.hp == 0) == (actor.key in world.dead_common), "Estado de morte divergente.")
    _require(all(isinstance(key, str) and phase in (1, 2, 3) for key, phase in world.boss_phases.items()),
             "Fases de chefe inválidas.")
    _require(world.ending in ("", "maintain", "extinguish", "transform") and type(world.credits_seen) is bool, "Desfecho inválido.")
    _require(not world.ending or "last_ember_custodian" in world.defeated_bosses, "Desfecho sem vitória.")
    _require(not world.credits_seen or bool(world.ending), "Créditos sem desfecho.")
    for boss in bosses:
        _require(_integer(boss.hazard_step) and boss.hazard_step < 720, "Timer de hazard inválido.")
        _require(boss.phase != 3 or boss.id == "last_ember_custodian", "Terceira fase não suportada.")
        _require(boss.phase in (1, 2, 3) and _vector(boss.position) and _finite(boss.yaw), "Chefe inválido.")
        _require(world.boss_phases.get(boss.id) == boss.phase, "Fase divergente.")
        _require(type(boss.active) is bool and all(_integer(getattr(boss, name)) for name in (
            "intro_remaining", "transition_remaining", "death_remaining", "punish_cooldown",
            "grab_cooldown", "aoe_cooldown", "pause_remaining", "blocking_steps", "close_steps")),
            "Timers de chefe inválidos.")
        _require((boss.fighter is None) == (boss.id in world.defeated_bosses), "Estado de derrota divergente.")
        if boss.fighter is not None:
            _validate_fighter(boss.fighter, next({"player"} | {a.key for a in area.actors} | {b.id for b in area.bosses} for area in areas if boss in area.bosses))
            _require((boss.fighter.hp == 0) == (boss.death_remaining > 0), "Morte do chefe divergente.")
        _require(boss.last_move == "" or boss.last_move in {
            "slow_overhead", "wide_sweep", "backstep_punish", "forge_grab", "fire_aoe_ring",
            "tide_strike", "tide_sweep", "tide_bolt", "tide_grasp", "tide_nova"},
            "Movimento de chefe inválido.")


def _validate_fighter(fighter: FighterSnapshot, keys: set[str]) -> None:
    _require(fighter.weapon_id in WEAPONS, "Arma desconhecida.")
    _require(_integer(fighter.upgrade) and fighter.upgrade in WEAPONS[fighter.weapon_id].upgrade_levels,
             "Melhoria fora do catálogo.")
    _require(_finite(fighter.hp, fighter.stamina, fighter.poise), "Recursos não finitos.")
    _require(_finite(*asdict(fighter.resist).values()), "Resistências inválidas.")
    maximum = fighter.stats.max_hp * (.7 if "curse" in fighter.active_status else 1)
    _require(0 <= fighter.hp <= maximum and 0 <= fighter.stamina <= fighter.stats.max_stamina, "Recursos inválidos.")
    effects = {effect.value for effect in StatusEffect}
    _require(set(fighter.buildup) <= effects and set(fighter.active_status) <= effects, "Condição desconhecida.")
    _require(all(_finite(value) and 0 <= value < 100 for value in fighter.buildup.values()), "Acúmulo inválido.")
    _require(all(_integer(time, 1) or (effect == "curse" and time == -1)
                 for effect, time in fighter.active_status.items()), "Duração de condição inválida.")
    _require(all(_integer(time) for time in (fighter.regen_delay, fighter.stagger_steps,
                                           fighter.riposte_steps, fighter.hit_steps,
                                           fighter.stagger_cooldown_steps, fighter.knockdown_steps,
                                           fighter.riposte_hits_remaining)), "Timer inválido.")
    _require(_integer(fighter.parry_step, -1) and fighter.parry_step < PARRY_RECOVERY_STEPS,
             "Timer de parry inválido.")
    _require(all(type(value) is bool for value in (fighter.blocking, fighter.invulnerable)), "Guarda inválida.")
    attack = fighter.attack
    if attack is not None:
        definition = attack.definition
        _require(definition.kind in AttackKind and _integer(definition.windup) and
                 _integer(definition.active, 1) and _integer(definition.recovery), "Definição de ataque inválida.")
        definitions = {item.kind: item for item in WEAPONS[fighter.weapon_id].attacks}
        definitions.update({spell.attack.kind: spell.attack for spell in SPELLS.values()
                            if spell.can_cast(fighter.stats, fighter.weapon_id)})
        if definition.kind in (spell.attack.kind for spell in SPELLS.values()):
            _require(definition == definitions.get(definition.kind), "Conjuração incompatível com o catálogo.")
        _require(definition.kind in definitions and
                 replace(definition, packet=definitions[definition.kind].packet) == definitions[definition.kind],
                 "Ataque incompatível com o catálogo.")
        _require(_finite(definition.stamina, definition.reach, definition.arc) and
                 definition.stamina >= 0 and definition.reach > 0 and type(definition.parryable) is bool,
                 "Parâmetros de ataque inválidos.")
        _require(definition.hitbox_kind in HitboxKind and type(definition.blockable) is bool
                 and _finite(definition.sphere_radius_start, definition.sphere_radius_end,
                             definition.block_damage_fraction)
                 and 0 <= definition.sphere_radius_start <= definition.sphere_radius_end
                 and 0 <= definition.block_damage_fraction <= 1 and _integer(definition.knockdown_steps),
                 "Volume de ataque inválido.")
        _require(_finite(definition.healing) and definition.healing >= 0, "Cura inválida.")
        _require(all(_finite(value) and value >= 0 for value in asdict(definition.packet).values()),
                 "Pacote de dano inválido.")
        _require(definition.cancel_from is None or
                 (_integer(definition.cancel_from) and definition.cancel_from < definition.duration),
                 "Janela de combo inválida.")
        _require(definition.status is None or
                 (definition.status[0] in StatusEffect and _finite(definition.status[1])
                  and definition.status[1] >= 0), "Efeito de ataque inválido.")
        _require(_integer(attack.age) and attack.age < definition.duration, "Timer de ataque inválido.")
        _require((attack.aim is None or _vector(attack.aim)) and type(attack.fired) is bool,
                 "Mira de conjuração inválida.")
        _require(set(attack.hit_targets) <= keys and (attack.victim is None or attack.victim in keys),
                 "Referência de alvo inválida.")
