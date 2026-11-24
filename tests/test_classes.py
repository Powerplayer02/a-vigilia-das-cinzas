"""Conteúdo, equipamento e magias são validados sem janela nem serviços do jogo."""

from pathlib import Path
import shutil
import pytest
from vigilia.model.classes import CLASS_ORDER, CHARACTER_CLASSES, load_classes
from vigilia.model.characters import create_character, starting_inventory
from vigilia.model.items import PLAYER_WEAPON_IDS, WEAPONS
from vigilia.model.spells import SPELLS

ROOT = Path(__file__).resolve().parents[1]


def test_catalog_order_and_class_loadouts_match_the_blueprint():
    assert tuple(CHARACTER_CLASSES) == CLASS_ORDER
    assert [profile.starting_weapon for profile in CHARACTER_CLASSES.values()] == ["axe", "longsword", "katana", "staff", "mace"]
    for identity, profile in CHARACTER_CLASSES.items():
        _, stats, weapon_id = create_character("Vesper", identity, {"vigor": 10})
        inventory = starting_inventory(identity)
        assert inventory.equip(weapon_id, stats).spec_id == profile.starting_weapon
        assert inventory.equipped_gear == profile.starting_gear
        assert inventory.spells == profile.starting_spells
        assert all(SPELLS[key].can_cast(stats, weapon_id) for key in inventory.spells)
        assert sum(getattr(profile.base_stats, key) for key in profile.base_stats.__dataclass_fields__) == 60
        assert inventory.equip_weight <= stats.max_equip_load


def test_each_new_character_gets_independent_inventory_and_upgrades():
    first, second = starting_inventory("mage"), starting_inventory("mage")
    first.items["shard"] = 0
    first.upgrades["staff"] = 2
    assert second.items["shard"] == 3 and second.upgrades["staff"] == 0
    assert dict(CHARACTER_CLASSES["mage"].starting_items)["shard"] == 3


@pytest.mark.parametrize("old,new", [
    ('weapon = "staff"', 'weapon = "unknown"'),
    ('staff = 1', 'staff = 0'),
    ('staff = 1', 'staff = true'),
    ('intelligence = 16', 'intelligence = 6'),
    ('spells = ["ember_shard"]', 'spells = ["unknown"]'),
    ('gear = ["robe"]', 'gear = ["robe", "robe"]'),
    ('version = 1', 'version = 2'),
    ('gear = ["robe"]', 'gear = "robe"'),
])
def test_invalid_content_fails_before_creation(tmp_path, old, new):
    folder = tmp_path / "classes"
    shutil.copytree(ROOT / "data/classes", folder)
    mage = folder / "mage.toml"
    mage.write_text(mage.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
    with pytest.raises(ValueError):
        load_classes(folder)


def test_missing_class_and_unmet_spell_requirements_are_rejected(tmp_path):
    folder = tmp_path / "classes"
    shutil.copytree(ROOT / "data/classes", folder)
    (folder / "cleric.toml").unlink()
    with pytest.raises(ValueError):
        load_classes(folder)


@pytest.mark.parametrize("points", [None, [], {"vigor": True, "endurance": 9}, {"vigor": 1.5, "faith": 8.5}])
def test_allocation_requires_exactly_ten_integer_points(points):
    with pytest.raises(ValueError):
        create_character("Vesper", "mage", points)


def test_all_five_weapons_have_a_complete_usable_moveset():
    from vigilia.player.movesets import for_weapon
    for key in PLAYER_WEAPON_IDS:
        moveset = for_weapon(WEAPONS[key].instantiate())
        assert len(moveset.light) in (2, 3) and moveset.heavy.stamina > 0
        assert moveset.riposte and moveset.backstab and moveset.running


def test_every_starting_item_and_spell_has_names_and_descriptions_in_both_languages():
    import tomllib
    for language in ("pt_BR", "en_US"):
        catalog = tomllib.loads((ROOT / "data/locale" / (language + ".toml")).read_text(encoding="utf-8"))
        for identity, profile in CHARACTER_CLASSES.items():
            assert catalog[f"class.{identity}.name"] and catalog[f"class.{identity}.desc"]
            for item, _ in profile.starting_items:
                assert catalog["item." + item] and catalog["item." + item + ".desc"]
        assert catalog["control.cast"] and catalog["hud.spell"]
