"""Round-trip completo com controladores puros e rollback em gravação parcial."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from combat_fakes import PhysicsFake
from vigilia.combat.attack import Attack
from vigilia.combat.fighter import Fighter
from vigilia.combat.status import StatusEffect
from vigilia.core.mathx import Transform, Vec3
from vigilia.core.timing import TIMING_VERSION
from vigilia.core.types import Action, HeldState, InputEdge
from vigilia.model.inventory import Inventory, RollTier
from vigilia.model.items import AXE_SPEC, PRACTICE_SPEC, TRAINING_STATS
from vigilia.model.progression import Bloodstain
from vigilia.model.snapshots import (
    SNAPSHOT_VERSION, ActorSnapshot, PlayerSnapshot, WorldSnapshot, SaveSnapshot,
)
from vigilia.model.stats import StatsBlock
from vigilia.player.controller import PlayerController
from vigilia.player.state_machine import CombatController
from vigilia.save.service import SaveService
from vigilia.save.database import SCHEMA_VERSION
from vigilia.save.serializers import SaveFormatError, encode, decode


def full_snapshot(rolling: bool = False) -> SaveSnapshot:
    inventory = Inventory()
    inventory.upgrades["axe"] = 2
    stats = StatsBlock(vigor=15, endurance=12, strength=18, intelligence=14, faith=13, luck=22)
    fighter = Fighter(0, inventory.equip("axe", stats), stats)
    fighter.hp, fighter.stamina, fighter.poise = 73.2, 90, 12.5
    fighter.status.active = {StatusEffect.POISON: 51, StatusEffect.CURSE: -1}
    fighter.status.buildup = {StatusEffect.BLEED: 42.5}
    fighter.regen_delay, fighter.hit_steps = 13, 4
    body = PhysicsFake()
    transform = Transform(Vec3(1.2, -2.5, 1.1), .8)
    motion = PlayerController(body, transform)
    controller = CombatController(fighter, transform, inventory)
    keys = {7: "player", 13: "dummy_a", 31: "dummy_b"}
    if rolling:
        motion.update(HeldState(move_y=1), InputEdge(Action.ROLL, True), Vec3(0, 1), Vec3(1, 0),
                      locked=False, fighter=fighter, mobility=RollTier.HEAVY)
        for _ in range(4):
            motion.update(HeldState(move_y=1), None, Vec3(0, 1), Vec3(1, 0),
                          locked=False, fighter=fighter, mobility=RollTier.HEAVY)
    else:
        fighter.attack = Attack(AXE_SPEC.attacks[0], 18, {13})
        controller.combo_buffered = True
    dummy_a = Fighter(1, PRACTICE_SPEC.instantiate(), TRAINING_STATS)
    dummy_a.attack = Attack(PRACTICE_SPEC.attacks[0], age=9)
    dummy_a.stagger_steps = 3
    dummy_b = Fighter(1, PRACTICE_SPEC.instantiate(), TRAINING_STATS)
    dummy_b.hp = 0
    stain = Bloodstain(Vec3(8, 3, 1), 187)
    player = PlayerSnapshot(
        motion.to_snapshot(), fighter.to_snapshot(keys), controller.to_snapshot(), 4, 239,
        stain.position, stain.souls, inventory.items.copy(), inventory.upgrades.copy(),
        inventory.equipped_weapon, inventory.equipped_gear,
    )
    world = WorldSnapshot(
        ("patio_da_vigilia",), ("patio_sul", "patio_norte"), "patio_norte", ("dummy_b",),
        ("abadessa",), ("portao",), ("fragmento_1",),
        (ActorSnapshot("dummy_a", Vec3(0, 2.4, 1), 3.14, dummy_a.to_snapshot(keys)),
         ActorSnapshot("dummy_b", Vec3(-6.5, 5.4, 1), 3.14, dummy_b.to_snapshot(keys))),
        39, 0,
    )
    return SaveSnapshot(SNAPSHOT_VERSION, TIMING_VERSION, player, world)


@pytest.mark.parametrize("rolling", [False, True])
def test_complete_round_trip_reopens_db_and_restores_public_controller_contracts(tmp_path, rolling) -> None:
    path = tmp_path / "progresso.sqlite3"
    original = full_snapshot(rolling)
    SaveService(path).save(1, original)
    reopened = SaveService(path)
    loaded = reopened.load()
    assert loaded == original
    fighter = Fighter(0, AXE_SPEC.instantiate())
    ids = {"player": 100, "dummy_a": 200, "dummy_b": 300}
    fighter.from_snapshot(loaded.player.fighter, ids)
    motion = PlayerController(PhysicsFake(), Transform())
    motion.from_snapshot(loaded.player.motion)
    controller = CombatController(fighter, motion.transform)
    controller.from_snapshot(loaded.player.controls)
    assert motion.to_snapshot() == original.player.motion
    assert fighter.to_snapshot({value: key for key, value in ids.items()}) == original.player.fighter
    assert controller.to_snapshot() == original.player.controls
    if not rolling:
        assert fighter.attack.hit_targets == {200}
    else:
        assert motion.dodging
    with reopened.repository.database.connect() as connection:
        assert connection.execute("PRAGMA synchronous").fetchone()[0] == 1
        assert connection.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0] == SCHEMA_VERSION


def test_world_write_failure_rolls_back_player_and_metadata(tmp_path) -> None:
    service = SaveService(tmp_path / "atomic.sqlite3")
    first = full_snapshot()
    service.save(1, first)
    with service.repository.database.connect() as connection:
        connection.execute(
            "CREATE TRIGGER reject_world BEFORE UPDATE ON world "
            "BEGIN SELECT RAISE(ABORT, 'simulated failure'); END")
    second = replace(first, player=replace(first.player, souls=999),
                     world=replace(first.world, collected_items=("novo",)))
    with pytest.raises(sqlite3.IntegrityError):
        service.save(1, second)
    assert service.load() == first


def test_concurrent_saves_leave_matching_player_and_world(tmp_path) -> None:
    service = SaveService(tmp_path / "parallel.sqlite3")
    first = full_snapshot()
    def save(index):
        snapshot = replace(first, player=replace(first.player, souls=index),
                           world=replace(first.world, collected_items=(str(index),)))
        service.save(1, snapshot)
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(save, range(8)))
    loaded = service.load()
    assert loaded.world.collected_items == (str(loaded.player.souls),)


def test_incompatible_timing_and_corrupt_json_are_rejected(tmp_path) -> None:
    service = SaveService(tmp_path / "invalid.sqlite3")
    snapshot = full_snapshot()
    service.save(1, snapshot)
    with pytest.raises(SaveFormatError):
        service.save(1, replace(snapshot, timing_version=999))
    assert service.load() == snapshot
    with service.repository.database.connect() as connection:
        connection.execute("UPDATE player SET payload=?", ('{"bad":true}',))
    with pytest.raises(SaveFormatError):
        service.load()


def test_missing_world_row_and_incompatible_attack_are_rejected(tmp_path) -> None:
    service = SaveService(tmp_path / "missing.sqlite3")
    snapshot = full_snapshot()
    service.save(1, snapshot)
    with service.repository.database.connect() as connection:
        connection.execute("DELETE FROM world")
    with pytest.raises(SaveFormatError):
        service.load()
    attack = snapshot.player.fighter.attack
    altered = replace(attack, definition=replace(attack.definition, cancel_from=999))
    fighter = replace(snapshot.player.fighter, attack=altered)
    with pytest.raises(SaveFormatError):
        service.save(1, replace(snapshot, player=replace(snapshot.player, fighter=fighter)))


def test_serialization_has_canonical_order_and_no_live_references() -> None:
    snapshot = full_snapshot()
    first = encode(snapshot)
    assert first == encode(snapshot)
    snapshot.player.items["shard"] = 17
    assert first != encode(snapshot)


def test_transient_enemies_do_not_enter_snapshot_or_attack_references(tmp_path) -> None:
    import json
    from vigilia.entities.ecs import World
    from vigilia.entities.archetypes import make_enemy
    from vigilia.model.enemies import ENEMIES
    snapshot = full_snapshot()
    runtime = World()
    for profile in ENEMIES.values():
        make_enemy(runtime, profile.id, Vec3(3, 3, 1), PhysicsFake(),
                   Fighter(1, profile.weapon.instantiate(), profile.stats), (Vec3(3, 3, 1),))
    fighter = Fighter(0, AXE_SPEC.instantiate(2))
    fighter.from_snapshot(snapshot.player.fighter, {"player": 7, "dummy_a": 13, "dummy_b": 31})
    fighter.attack.hit_targets.add(999)
    fighter.attack.victim = 999
    saved = fighter.to_snapshot({7: "player", 13: "dummy_a", 31: "dummy_b"})
    assert saved.hit_steps == snapshot.player.fighter.hit_steps
    assert saved.attack.hit_targets == ("dummy_a",) and saved.attack.victim is None
    snapshot = replace(snapshot, player=replace(snapshot.player, fighter=saved))
    service = SaveService(tmp_path / "transient.sqlite3")
    service.save(1, snapshot)
    loaded = service.load()
    player_json, world_json = encode(loaded)
    assert len(json.loads(world_json)["actors"]) == 2
    assert all(key not in world_json for key in ("nav_agent", "ai_state", "next_repath", "combo_index"))


def test_previous_v42_payload_loads_with_default_new_fields() -> None:
    import json
    snapshot = full_snapshot()
    player_json, world_json = encode(snapshot)
    player, world = json.loads(player_json), json.loads(world_json)
    fighters = [player["fighter"], *(actor["fighter"] for actor in world["actors"])]
    for fighter in fighters:
        fighter.pop("stagger_cooldown_steps")
        if fighter["attack"] is not None:
            fighter["attack"]["definition"].pop("ranged")
    loaded = decode(snapshot.version, snapshot.timing_version, json.dumps(player), json.dumps(world))
    assert loaded == snapshot


@pytest.mark.parametrize("dead", [False, True])
def test_boss_save_round_trip_preserves_live_hp_phase_and_omits_dead_hp(tmp_path, dead):
    import json
    from boss_fakes import encounter
    e = encounter()
    e.boss.phase = 2
    e.fighter.hp = 0 if dead else 1450
    e.boss.active, e.boss.defeated = not dead, dead
    boss = e.boss.to_snapshot({e.player.id: "player", e.entity.id: e.profile.id})
    original = full_snapshot()
    original = replace(original, world=replace(original.world, bosses=(boss,),
        boss_phases={e.profile.id: 2}, defeated_bosses=(e.profile.id,) if dead else ()))
    service = SaveService(tmp_path / "boss.sqlite3")
    service.save(1, original)
    loaded = service.load()
    assert loaded == original
    if dead:
        assert json.loads(encode(loaded)[1])["bosses"][0]["fighter"] is None
        assert loaded.world.defeated_bosses == (e.profile.id,)
    else:
        assert loaded.world.bosses[0].fighter.hp == 1450
        e.boss.from_snapshot(loaded.world.bosses[0], {"player": 100, e.profile.id: e.entity.id}, False)
        assert e.fighter.hp == 1450 and e.boss.phase == 2


def test_pre_boss_payload_defaults_all_additive_fields():
    import json
    original = full_snapshot()
    p, w = (json.loads(part) for part in encode(original))
    w.pop("bosses")
    w.pop("boss_phases")
    for fighter in [p["fighter"], *(actor["fighter"] for actor in w["actors"])]:
        fighter.pop("knockdown_steps")
        fighter.pop("riposte_hits_remaining")
        if fighter["attack"]:
            for key in ("hitbox_kind", "sphere_radius_start", "sphere_radius_end", "blockable",
                        "block_damage_fraction", "knockdown_steps"):
                fighter["attack"]["definition"].pop(key)
    loaded = decode(original.version, original.timing_version, json.dumps(p), json.dumps(w))
    assert loaded == original
