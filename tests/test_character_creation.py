"""Origens equilibradas e validação dos dez pontos livres."""

import pytest
from vigilia.model.characters import CHARACTER_CLASSES, create_character
from vigilia.model.items import PLAYER_WEAPON_IDS


def test_five_distinct_classes_use_existing_weapons_and_accept_exactly_ten_points():
    assert len(CHARACTER_CLASSES) == 5
    assert len({profile.base_stats for profile in CHARACTER_CLASSES.values()}) == 5
    for class_id, profile in CHARACTER_CLASSES.items():
        name, stats, weapon = create_character("  Vésper  ", class_id, {"vigor": 10})
        assert name == "Vésper" and stats.vigor == profile.base_stats.vigor + 10
        assert weapon in PLAYER_WEAPON_IDS and weapon == profile.starting_weapon


@pytest.mark.parametrize("name,class_id,points", [("", "warrior", {"vigor": 10}),
    ("A\nB", "warrior", {"vigor": 10}), ("A", "unknown", {"vigor": 10}),
    ("A", "warrior", {"vigor": 9}), ("A", "warrior", {"vigor": 11}),
    ("A", "warrior", {"vigor": -1, "luck": 11}), ("A", "warrior", {"x": 10})])
def test_invalid_creation_is_rejected(name, class_id, points):
    with pytest.raises(ValueError):
        create_character(name, class_id, points)


def class_snapshot(identity):
    from dataclasses import replace
    from test_save import full_snapshot
    from combat_fakes import PhysicsFake
    from vigilia.core.mathx import Transform
    from vigilia.combat.fighter import Fighter
    from vigilia.model.characters import starting_inventory
    from vigilia.player.controller import PlayerController
    from vigilia.player.state_machine import CombatController
    allocation = {"vigor": 3, "endurance": 7}
    name, stats, weapon = create_character("Vésper", identity, allocation)
    inventory = starting_inventory(identity)
    fighter = Fighter(0, inventory.equip(weapon, stats), stats)
    original = full_snapshot()
    player = replace(original.player, motion=PlayerController(PhysicsFake(), Transform()).to_snapshot(),
        fighter=fighter.to_snapshot({7: "player"}), controls=CombatController(fighter, Transform(), inventory).to_snapshot(),
        level=1, character_name=name, character_class=identity, starting_allocation=allocation,
        items=inventory.items.copy(), upgrades=inventory.upgrades.copy(), equipped_weapon=weapon,
        equipped_gear=inventory.equipped_gear)
    return replace(original, player=player)


@pytest.mark.parametrize("identity", tuple(CHARACTER_CLASSES))
def test_creation_stats_equipment_spells_and_allocation_survive_reopening_database(identity, tmp_path):
    from vigilia.save.service import SaveService
    from vigilia.model.inventory import Inventory
    snapshot = class_snapshot(identity)
    path = tmp_path / "slots.sqlite3"
    SaveService(path).save(1, snapshot)
    restored = SaveService(path).load(1)
    assert restored == snapshot
    inventory = Inventory(restored.player.items, restored.player.upgrades, restored.player.equipped_weapon, restored.player.equipped_gear)
    assert inventory.spells == CHARACTER_CLASSES[identity].starting_spells
    assert restored.player.starting_allocation == {"vigor": 3, "endurance": 7}


def test_old_mage_save_keeps_its_original_equipment_without_receiving_free_items():
    import json
    from test_save import full_snapshot
    from vigilia.save.serializers import encode, decode
    snapshot = full_snapshot()
    player_json, world_json = encode(snapshot)
    player = json.loads(player_json)
    player.pop("starting_allocation")
    player["character_class"] = "mage"
    attack = player["fighter"]["attack"]
    attack.pop("aim")
    attack.pop("fired")
    restored = decode(snapshot.version, snapshot.timing_version, json.dumps(player), world_json)
    assert restored.player.starting_allocation == {}
    assert restored.player.items == snapshot.player.items and "staff" not in restored.player.items
    assert restored.player.fighter == snapshot.player.fighter


@pytest.mark.parametrize("identity,spell_id,age,fired", [("mage", "ember_shard", 12, False),
    ("mage", "ember_shard", 23, True), ("cleric", "mending_light", 30, False)])
def test_cast_in_progress_round_trips_without_losing_aim_or_repeating_effect(identity, spell_id, age, fired):
    from dataclasses import replace
    from vigilia.combat.fighter import Fighter
    from vigilia.combat.attack import Attack
    from vigilia.core.mathx import Vec3
    from vigilia.model.items import WEAPONS
    from vigilia.model.spells import SPELLS
    from vigilia.save.serializers import encode, decode
    snapshot = class_snapshot(identity)
    weapon = WEAPONS[snapshot.player.equipped_weapon].instantiate()
    fighter = Fighter(0, weapon, snapshot.player.fighter.stats)
    fighter.attack = Attack(SPELLS[spell_id].attack, age=age, aim=Vec3(4, 5, 1), fired=fired)
    if identity == "cleric":
        fighter.attack.hit_targets.add(7)  # cura já aplicada no frame ativo
    snapshot = replace(snapshot, player=replace(snapshot.player, fighter=fighter.to_snapshot({7: "player"})))
    restored = decode(snapshot.version, snapshot.timing_version, *encode(snapshot))
    fighter.from_snapshot(restored.player.fighter, {"player": 7})
    assert fighter.attack.aim == Vec3(4, 5, 1) and fighter.attack.fired == fired
    assert fighter.attack.age == age and (7 in fighter.attack.hit_targets) == (identity == "cleric")


def test_corrupt_spell_or_allocation_is_rejected_before_load():
    from dataclasses import replace
    from vigilia.model.snapshots import AttackSnapshot
    from vigilia.model.spells import SPELLS
    from vigilia.save.serializers import validate, SaveFormatError
    snapshot = class_snapshot("mage")
    for allocation in ({"vigor": 9}, {"unknown": 10}, {"vigor": True}):
        with pytest.raises(SaveFormatError):
            validate(replace(snapshot, player=replace(snapshot.player, starting_allocation=allocation)))
    definition = replace(SPELLS["ember_shard"].attack, healing=999)
    fighter = replace(snapshot.player.fighter, attack=AttackSnapshot(definition, 0, (), None))
    with pytest.raises(SaveFormatError):
        validate(replace(snapshot, player=replace(snapshot.player, fighter=fighter)))
    definition = SPELLS["ember_shard"].attack
    fighter = replace(snapshot.player.fighter, attack=AttackSnapshot(definition, 0, (), None))
    with pytest.raises(SaveFormatError):
        validate(replace(snapshot, player=replace(snapshot.player, fighter=fighter,
            items={key: count for key, count in snapshot.player.items.items() if key != "ember_shard"})))
