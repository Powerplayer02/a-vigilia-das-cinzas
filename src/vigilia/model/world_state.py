"""Flags persistentes por identificador estável."""

from dataclasses import dataclass, field


@dataclass(slots=True)
class WorldState:
    discovered_areas: set[str] = field(default_factory=set)
    visited_bonfires: set[str] = field(default_factory=lambda: {"patio_sul"})
    last_bonfire: str = "patio_sul"
    dead_common: set[str] = field(default_factory=set)
    defeated_bosses: set[str] = field(default_factory=set)
    opened_shortcuts: set[str] = field(default_factory=set)
    collected_items: set[str] = field(default_factory=set)
    boss_phases: dict[str, int] = field(default_factory=dict)

    ending: str = ""
    credits_seen: bool = False

    @property
    def bonfires_discovered(self) -> tuple[str, ...]:
        return tuple(sorted(self.visited_bonfires))
