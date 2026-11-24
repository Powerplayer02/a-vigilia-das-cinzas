"""A ampliação da arena preserva a capacidade de vinte inimigos no Pátio."""

from vigilia.world.arena import enemy_spawns, nav_grid


def test_twenty_spawns_are_walkable_separated_and_inside_patio():
    points, grid = enemy_spawns(20), nav_grid()
    assert len(points) == 20
    assert all(grid.walkable(grid.to_cell(point)) and -3 < point.y < 12 for point in points)
    assert all((point - other).length() > 1.5 for index, point in enumerate(points) for other in points[index + 1:])
