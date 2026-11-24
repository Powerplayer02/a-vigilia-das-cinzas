"""Limites exatos de carga, requisitos e consumo atômico de melhoria."""

from copy import deepcopy

import pytest

from vigilia.model.inventory import Inventory, RollTier, roll_tier
from vigilia.model.progression import Progression
from vigilia.model.stats import StatsBlock


@pytest.mark.parametrize(("weight", "tier"), [
    (29.999, RollTier.FAST), (30, RollTier.MID), (69.999, RollTier.MID), (70, RollTier.HEAVY),
])
def test_roll_thresholds(weight, tier) -> None:
    assert roll_tier(weight, 100) == tier


def test_inventory_weight_and_requirements_are_distinct_from_equipped_load() -> None:
    inventory = Inventory()
    weight = inventory.equip_weight
    inventory.items["shard"] = 100000
    assert inventory.equip_weight == weight
    assert inventory.total_weight > 1000
    with pytest.raises(ValueError):
        inventory.equip("axe", StatsBlock(strength=1))
    assert inventory.equipped_weapon == "longsword"
    assert inventory.equip("axe", StatsBlock()).spec_id == "axe"


def test_upgrade_consumes_both_costs_or_changes_nothing() -> None:
    inventory, progress = Inventory(), Progression(souls=100)
    weapon = inventory.upgrade(progress)
    assert weapon.upgrade == 1
    assert inventory.items["shard"] == 2 and progress.souls == 20
    before = deepcopy(inventory)
    with pytest.raises(ValueError):
        inventory.upgrade(progress)
    assert inventory == before and progress.souls == 20
