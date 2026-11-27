"""Projeções imutáveis usadas pela apresentação, sem objetos vivos do domínio."""

from dataclasses import dataclass
from enum import StrEnum, auto
from vigilia.core.mathx import Vec3


class ItemCategory(StrEnum):
    ALL = "all"
    WEAPON = "weapon"
    GEAR = "gear"
    MATERIAL = "material"
    CONSUMABLE = "consumable"
    MAGIC = "magic"


@dataclass(frozen=True, slots=True)
class VitalsView:
    hp: float
    max_hp: float
    stamina: float
    max_stamina: float
    souls: int
    weapon: str
    quick_item: str = "Vazio"
    quick_count: int = 0
    message: str = ""
    quick_is_spell: bool = False
    quick_hint: str = ""
    spell_name: str = ""
    spell_hint: str = ""
    spell_kind: str = ""
    spell_stamina: float = 0
    spell_remaining: float = 0
    spell_duration: float = 0
    spell_ready: bool = False
    weapon_icon: str = "sword"


@dataclass(frozen=True, slots=True)
class BossView:
    name: str
    hp: float
    max_hp: float
    phase: int


@dataclass(frozen=True, slots=True)
class StatusView:
    id: str
    name: str
    icon: str
    stacks: int
    buildup: float = 0
    seconds: int = 0


@dataclass(frozen=True, slots=True)
class StatView:
    id: str
    name: str
    value: int


@dataclass(frozen=True, slots=True)
class StatsView:
    level: int
    souls: int
    attributes: tuple[StatView, ...]
    max_hp: float
    max_stamina: float
    poise: float
    weight: float
    capacity: float
    mobility: str
    resistances: tuple[tuple[str, float], ...]
    can_level: bool


@dataclass(frozen=True, slots=True)
class ItemView:
    id: str
    name: str
    category: ItemCategory
    quantity: int
    weight: float
    damage: float = 0
    scaling: str = "—"
    requirements: str = "—"
    equipped: bool = False
    equippable: bool = False
    description: str = ""


@dataclass(frozen=True, slots=True)
class EquipmentView:
    weapon: ItemView
    gear: tuple[ItemView, ...]
    weight: float
    capacity: float


class UICommandKind(StrEnum):
    RESUME = auto()
    EQUIP = auto()
    LEVEL_UP = auto()
    NEW_GAME = auto()
    CONTINUE = auto()
    LOAD_SLOT = auto()
    CREATE_CHARACTER = auto()
    OPEN_OPTIONS = auto()
    OPEN_CREDITS = auto()
    MAIN_MENU = auto()
    BACK = auto()
    QUIT = auto()
    SET_OPTION = auto()
    REBIND = auto()
    RESET_OPTIONS = auto()
    SELECT_NEW_SLOT = auto()
    DELETE_SLOT = auto()
    CHOOSE_ENDING = auto()


@dataclass(frozen=True, slots=True)
class UICommand:
    kind: UICommandKind
    argument: str = ""


Color = tuple[float, float, float, float]
Rect = tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class SlotView:
    slot: int
    name: str = ""
    level: int = 0
    playtime_sec: float = 0
    area_id: str = ""
    saved_at: str = ""
    occupied: bool = False
    class_id: str = ""
    created_at: str = ""

    @property
    def updated_at(self) -> str:
        return self.saved_at


@dataclass(frozen=True, slots=True)
class SlotDeletionView:
    slot: int
    name: str
    level: int
    class_id: str
    updated_at: str
    bloodstain_souls: int
    in_use: bool


@dataclass(frozen=True, slots=True)
class CharacterClassView:
    id: str
    name: str
    description: str
    weapon: str
    attributes: tuple[StatView, ...]
    gear: str = ""
    spells: str = ""


@dataclass(frozen=True, slots=True)
class MapRegionView:
    id: str
    bounds: Rect


@dataclass(frozen=True, slots=True)
class MapMarkerView:
    id: str
    position: Vec3


@dataclass(frozen=True, slots=True)
class OptionView:
    id: str
    label: str
    value: str
    numeric: float | None = None
    minimum: float = 0.
    maximum: float = 1.
