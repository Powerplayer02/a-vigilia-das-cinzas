"""Catálogo validado em TOML; os perfis não dependem de engine ou UI."""

from dataclasses import dataclass, fields
from pathlib import Path
import tomllib

from vigilia.model.items import WEAPONS, PLAYER_WEAPON_IDS, ITEM_WEIGHTS, GEAR_IDS
from vigilia.model.spells import SPELLS
from vigilia.model.stats import StatsBlock

CLASS_ORDER = ("warrior", "knight", "assassin", "mage", "cleric")


@dataclass(frozen=True, slots=True)
class CharacterClass:
    id: str
    base_stats: StatsBlock
    starting_weapon: str
    starting_items: tuple[tuple[str, int], ...]
    starting_gear: tuple[str, ...]
    starting_spells: tuple[str, ...]


def load_classes(directory: Path) -> dict[str, CharacterClass]:
    """Falha antes de iniciar o jogo se conteúdo referenciar equipamento inexistente."""
    result = {}
    stat_names = {field.name for field in fields(StatsBlock)}
    for path in sorted(directory.glob("*.toml")):
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        if (set(raw) != {"version", "id", "weapon", "gear", "spells", "stats", "items"}
                or not isinstance(raw["stats"], dict) or not isinstance(raw["items"], dict)
                or not isinstance(raw["gear"], list) or not isinstance(raw["spells"], list)
                or not isinstance(raw["id"], str) or not isinstance(raw["weapon"], str)
                or any(not isinstance(key, str) for key in raw["gear"] + raw["spells"])):
            raise ValueError(f"Schema de classe inválido: {path.name}")
        identity, stats = raw.get("id"), raw.get("stats", {})
        weapon, gear = raw.get("weapon"), tuple(raw.get("gear", ()))
        items, spells = raw.get("items", {}), tuple(raw.get("spells", ()))
        if (type(raw.get("version")) is not int or raw["version"] != 1 or identity not in CLASS_ORDER
                or identity in result or set(stats) != stat_names
                or any(type(value) is not int or not 1 <= value <= 89 for value in stats.values())
                or sum(stats.values()) != 60 or weapon not in PLAYER_WEAPON_IDS
                or not isinstance(items, dict) or not items.get(weapon)
                or any(key not in WEAPONS and key not in ITEM_WEIGHTS for key in items)
                or any(type(value) is not int or value < 1 for value in items.values())
                or len(gear) != len(set(gear)) or any(key not in GEAR_IDS or not items.get(key) for key in gear)
                or len(spells) != len(set(spells)) or len(spells) > 3
                or any(key not in SPELLS or not items.get(key) for key in spells)
                or set(items).intersection(SPELLS) != set(spells)):
            raise ValueError(f"Classe inválida: {path.name}")
        block = StatsBlock(**stats)
        if not block.meets(WEAPONS[weapon].requirements) or any(not SPELLS[key].can_cast(block, weapon) for key in spells):
            raise ValueError(f"Requisitos iniciais não atendidos: {path.name}")
        result[identity] = CharacterClass(identity, block, weapon, tuple(items.items()), gear, spells)
    if set(result) != set(CLASS_ORDER):
        raise ValueError("O catálogo precisa conter as cinco classes iniciais.")
    return {identity: result[identity] for identity in CLASS_ORDER}


CHARACTER_CLASSES = load_classes(Path(__file__).resolve().parents[3] / "data/classes")
