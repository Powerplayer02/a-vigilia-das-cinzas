"""Cinco origens, dez pontos livres e validação de criação."""

from dataclasses import replace, fields

from vigilia.model.stats import StatsBlock
from vigilia.model.items import WEAPONS
from vigilia.model.classes import CharacterClass, CHARACTER_CLASSES
from vigilia.model.inventory import Inventory


def starting_inventory(class_id: str) -> Inventory:
    profile = CHARACTER_CLASSES[class_id]
    return Inventory(dict(profile.starting_items),
        {key: 0 for key, _ in profile.starting_items if key in WEAPONS},
        profile.starting_weapon, profile.starting_gear)


def validate_name(name: str) -> str:
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 24 or not name.strip().isprintable():
        raise ValueError("character.invalid_name")
    return name.strip()


def create_character(name: str, class_id: str, allocation: dict[str, int]) -> tuple[str, StatsBlock, str]:
    name = validate_name(name)
    if not isinstance(class_id, str) or class_id not in CHARACTER_CLASSES:
        raise ValueError("character.invalid_class")
    names = {field.name for field in fields(StatsBlock)}
    if (not isinstance(allocation, dict) or set(allocation) - names or any(type(value) is not int or value < 0 for value in allocation.values())
            or sum(allocation.values()) != 10):
        raise ValueError("character.allocate_ten")
    profile = CHARACTER_CLASSES[class_id]
    stats = replace(profile.base_stats, **{key: getattr(profile.base_stats, key) + value for key, value in allocation.items()})
    if any(getattr(stats, key) > 99 for key in names) or not stats.meets(WEAPONS[profile.starting_weapon].requirements):
        raise ValueError("character.invalid_stats")
    return name, stats, profile.starting_weapon
