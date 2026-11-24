"""A* e suavização conservadora, independentes da física e da renderização."""

import heapq
import math

from vigilia.core.mathx import Vec3
from vigilia.core.navigation import Cell, NavGrid


def line_of_sight(grid: NavGrid, start: Cell, goal: Cell) -> bool:
    """Verifica o segmento no grid, incluindo ambos os lados de quinas."""
    x, y = start
    dx, dy = goal[0] - x, goal[1] - y
    steps = max(abs(dx), abs(dy)) * 4
    if not grid.walkable(start) or not grid.walkable(goal):
        return False
    previous = start
    for step in range(1, steps + 1):
        cell = (round(x + dx * step / steps), round(y + dy * step / steps))
        if not grid.walkable(cell):
            return False
        if cell[0] != previous[0] and cell[1] != previous[1]:
            if not grid.walkable((previous[0], cell[1])) or not grid.walkable((cell[0], previous[1])):
                return False
        previous = cell
    return True


def a_star(grid: NavGrid, start: Vec3, goal: Vec3) -> list[Vec3]:
    """Devolve waypoints suavizados. Uma rota impossível resulta em lista vazia."""
    source, target = grid.to_cell(start), grid.to_cell(goal)
    if not grid.walkable(source) or not grid.walkable(target):
        return []
    frontier = [(0.0, source)]
    costs = {source: 0.0}
    parents: dict[Cell, Cell] = {}
    closed: set[Cell] = set()
    while frontier:
        _, current = heapq.heappop(frontier)
        if current in closed:
            continue
        if current == target:
            path = [target]
            while path[-1] != source:
                path.append(parents[path[-1]])
            path.reverse()
            smoothed = [path[0]]
            cursor = 1
            while cursor < len(path):
                farthest = cursor
                for index in range(cursor + 1, len(path)):
                    if not line_of_sight(grid, smoothed[-1], path[index]):
                        break
                    farthest = index
                smoothed.append(path[farthest])
                cursor = farthest + 1
            return [grid.to_world(cell) for cell in smoothed[1:]] or [grid.to_world(target)]
        closed.add(current)
        x, y = current
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1),
                       (1, 1), (1, -1), (-1, 1), (-1, -1)):
            neighbor = x + dx, y + dy
            if not grid.walkable(neighbor):
                continue
            if dx and dy and not (grid.walkable((x + dx, y)) and grid.walkable((x, y + dy))):
                continue
            candidate = costs[current] + (math.sqrt(2) if dx and dy else 1)
            if candidate < costs.get(neighbor, math.inf):
                costs[neighbor] = candidate
                parents[neighbor] = current
                heuristic = math.hypot(target[0] - neighbor[0], target[1] - neighbor[1])
                heapq.heappush(frontier, (candidate + heuristic, neighbor))
    return []
