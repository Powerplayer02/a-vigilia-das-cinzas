"""Cena declarativa: uma fonte para geometria, colisão, spawn e navegação."""

from dataclasses import dataclass
import math
from pathlib import Path
import tomllib

from vigilia.core.mathx import Vec3
from vigilia.core.navigation import NavGrid
from vigilia.model.areas import AREA_BOUNDS
from vigilia.world.arena import Block


@dataclass(frozen=True, slots=True)
class EnemySpawn:
    id: str
    profile: str
    position: Vec3


@dataclass(frozen=True, slots=True)
class Passage:
    id: str
    target: str
    position: Vec3
    arrival: Vec3
    label: str
    unlock: str = ""
    requires_boss: str = ""
    requires_flag: str = ""


@dataclass(frozen=True, slots=True)
class Area:
    id: str
    spawn: Vec3
    music: str
    fog_color: tuple[float, ...]
    light_color: tuple[float, ...]
    blocks: tuple[Block, ...]
    enemies: tuple[EnemySpawn, ...]
    fires: tuple[Vec3, ...]
    passages: tuple[Passage, ...]
    boss: dict

    def navigation(self, *, fog_closed=True) -> NavGrid:
        x, y, width, height = AREA_BOUNDS[self.id]
        size = .75
        obstacles = [(p.center.x, p.center.y, p.size.x / 2 + .55, p.size.y / 2 + .55)
            for p in self.blocks if p.collision and p.center.z + p.size.z / 2 > .27
            and p.center.z - p.size.z / 2 < 1.8]
        if self.boss and fog_closed:
            px, py, _ = self.boss["fog"]
            obstacles.append((px, py, 2.6, .8))
        cells = tuple(tuple(not any(abs(x + (i + .5) * size - cx) <= hx and
            abs(y + (j + .5) * size - cy) <= hy for cx, cy, hx, hy in obstacles)
            for i in range(math.ceil(width / size))) for j in range(math.ceil(height / size)))
        return NavGrid(cells, size, Vec3(x, y, .95))


class OpenGate:
    """Área sem barreira de chefe/atalho usa o mesmo contrato de interação."""
    blocked, opened, in_fight = False, True, False
    def __init__(self, state):
        self.state = state
    def can_open(self, position):
        return False
    def can_enter(self, position):
        return False
    def sync(self):
        pass
    def close(self):
        pass


def load_area(path: Path) -> Area:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    if data["id"] not in AREA_BOUNDS:
        raise ValueError("Área desconhecida.")
    blocks = tuple(Block(row["id"], Vec3(*row["center"]), Vec3(*row["size"]), tuple(row["color"]), row.get("collision", True))
        for row in data["blocks"])
    enemies = tuple(EnemySpawn(row["id"], row["profile"], Vec3(*row["position"])) for row in data["enemies"])
    passages = tuple(Passage(**{**row, "position": Vec3(*row["position"]), "arrival": Vec3(*row["arrival"])}) for row in data["passages"])
    area = Area(data["id"], Vec3(*data["spawn"]), data["music"], tuple(data["fog_color"]), tuple(data["light_color"]),
        blocks, enemies, tuple(Vec3(*p) for p in data["fires"]), passages, data.get("boss", {}))
    grid = area.navigation()
    if len({row.id for row in enemies}) != len(enemies) or not grid.walkable(grid.to_cell(area.spawn)):
        raise ValueError("Spawn ou identidade de ator inválidos.")
    for enemy in enemies:
        if not grid.walkable(grid.to_cell(enemy.position)):
            raise ValueError(f"Spawn dentro da colisão: {enemy.id}")
    return area
