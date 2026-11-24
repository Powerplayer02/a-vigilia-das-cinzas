"""Compara A* em cargas explícitas mantendo o mesmo código de busca."""

import json

from benchmark import isolated_pathfinding, nav_grid
from vigilia.core.navigation import NavGrid


def main():
    combined = nav_grid()
    patio = NavGrid(combined.cells[:36], combined.cell_size, combined.origin)
    cells = [(x, y) for y, row in enumerate(patio.cells) for x, free in enumerate(row) if free]
    pairs = [(patio.to_world(cells[index % len(cells)]),
              patio.to_world(cells[-1 - (index * 7) % len(cells)])) for index in range(200)]
    print(json.dumps({
        "patio_crop_current_geometry": isolated_pathfinding(patio, pairs),
        "combined_same_patio_endpoints": isolated_pathfinding(combined, pairs),
        "combined_mixed_endpoints": isolated_pathfinding(combined),
        "note": "Recorte do cenário atual, sem reconstrução da geometria histórica da 4.3.1.",
    }, indent=2))


if __name__ == "__main__":
    main()
