"""Dados de navegação compartilhados entre a área e a IA."""

import math
from dataclasses import dataclass

from vigilia.core.mathx import Vec3

Cell = tuple[int, int]


@dataclass(frozen=True, slots=True)
class NavGrid:
    cells: tuple[tuple[bool, ...], ...]
    cell_size: float
    origin: Vec3

    def walkable(self, cell: Cell) -> bool:
        x, y = cell
        return 0 <= y < len(self.cells) and 0 <= x < len(self.cells[0]) and self.cells[y][x]

    def to_world(self, cell: Cell) -> Vec3:
        return self.origin + Vec3((cell[0] + .5) * self.cell_size,
                                  (cell[1] + .5) * self.cell_size)

    def to_cell(self, position: Vec3) -> Cell:
        return (math.floor((position.x - self.origin.x) / self.cell_size),
                math.floor((position.y - self.origin.y) / self.cell_size))

    def nearest_walkable(self, position: Vec3) -> Cell | None:
        """Aproxima posições junto às paredes à célula livre mais próxima."""
        cell = self.to_cell(position)
        if self.walkable(cell):
            return cell
        candidates = [(cell[0] + dx, cell[1] + dy)
                      for dx in range(-3, 4) for dy in range(-3, 4)
                      if self.walkable((cell[0] + dx, cell[1] + dy))]
        return min(candidates, key=lambda item: (self.to_world(item) - position).length()) if candidates else None
