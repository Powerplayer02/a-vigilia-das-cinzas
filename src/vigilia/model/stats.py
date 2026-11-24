"""Atributos usados pelas regras de combate."""

from dataclasses import dataclass, fields


@dataclass(frozen=True, slots=True)
class StatsBlock:
    vigor: int = 10
    endurance: int = 10
    strength: int = 10
    dexterity: int = 10
    intelligence: int = 10
    faith: int = 10
    luck: int = 10

    def __post_init__(self) -> None:
        if any(type(getattr(self, item.name)) is not int or getattr(self, item.name) < 0
               for item in fields(self)):
            raise ValueError("Atributos precisam ser inteiros não negativos.")

    @property
    def max_hp(self) -> float:
        return 80 + self.vigor * 6

    @property
    def max_stamina(self) -> float:
        return 70 + self.endurance * 4

    @property
    def max_poise(self) -> float:
        return 20 + self.endurance * 2

    @property
    def max_equip_load(self) -> float:
        return 24 + self.endurance * 2

    @property
    def drop_multiplier(self) -> float:
        return 1 + min(self.luck, 99) * .01

    def meets(self, requirements: "StatsBlock") -> bool:
        return all(getattr(self, item.name) >= getattr(requirements, item.name) for item in fields(self))


@dataclass(frozen=True, slots=True)
class ResistBlock:
    physical_slash: float = 0
    physical_strike: float = 0
    physical_pierce: float = 0
    fire: float = 0
    magic: float = 0
    holy: float = 0
