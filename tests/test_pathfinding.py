"""Rotas, quinas e regiões desconectadas sem engine."""

from vigilia.ai.pathfinding import NavGrid, a_star, line_of_sight
from vigilia.core.mathx import Vec3


def test_path_around_column_has_clear_segments() -> None:
    rows = tuple(tuple(not (3 <= x <= 5 and 2 <= y <= 6) for x in range(10)) for y in range(9))
    grid = NavGrid(rows, 1, Vec3())
    start, end = Vec3(1.5, 4.5), Vec3(8.5, 4.5)
    route = a_star(grid, start, end)
    assert route
    assert grid.to_cell(route[-1]) == grid.to_cell(end)
    previous = grid.to_cell(start)
    for point in route:
        assert line_of_sight(grid, previous, grid.to_cell(point))
        previous = grid.to_cell(point)
    assert any(point.y < 2 or point.y >= 7 for point in route)


def test_diagonal_cannot_cut_blocked_corner() -> None:
    grid = NavGrid(((True, False), (False, True)), 1, Vec3())
    assert a_star(grid, Vec3(.5, .5), Vec3(1.5, 1.5)) == []
    assert not line_of_sight(grid, (0, 0), (1, 1))


def test_unreachable_or_blocked_goal_returns_empty_route() -> None:
    grid = NavGrid(((True, False, True), (True, False, True)), 1, Vec3())
    assert a_star(grid, Vec3(.5, .5), Vec3(2.5, .5)) == []
    assert a_star(grid, Vec3(.5, .5), Vec3(1.5, .5)) == []


def test_open_route_smooths_and_grid_coordinates_round_trip() -> None:
    grid = NavGrid(tuple((True,) * 8 for _ in range(8)), .75, Vec3(-3, -3, 1))
    path = a_star(grid, grid.to_world((0, 0)), grid.to_world((7, 7)))
    assert path == [grid.to_world((7, 7))]
    assert grid.to_cell(grid.to_world((3, 4))) == (3, 4)
