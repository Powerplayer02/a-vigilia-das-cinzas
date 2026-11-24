"""Geometria e pontos de interesse do Pátio de treinamento."""

from dataclasses import dataclass

from vigilia.core.events import AreaEnteredEvent, EventBus
from vigilia.core.mathx import Transform, Vec3
from vigilia.entities.components import LockOnTarget
from vigilia.entities.ecs import World
from vigilia.core.navigation import NavGrid


@dataclass(frozen=True, slots=True)
class Block:
    name: str
    center: Vec3
    size: Vec3
    tint: tuple[float, float, float, float]
    collision: bool = True


STONE = (0.27, 0.31, 0.34, 1)
TRIM = (0.36, 0.38, 0.39, 1)
FLOOR = (0.23, 0.26, 0.28, 1)
BRASS = (0.59, 0.39, 0.22, 1)
ARENA_ID = "patio_da_vigilia"
SPAWN = Vec3(0, -6.5, 1.02)
TARGETS = (Vec3(0, 2.4, 1), Vec3(-6.5, 5.4, 1), Vec3(6.2, 5.7, 1))
BRAZIERS = (Vec3(-3.8, -4.8, 0), Vec3(3.8, -4.8, 0), Vec3(0, 10.8, 0),
            Vec3(-1.7, -6.8, 0), Vec3(-8.5, 24, 0), Vec3(8.5, 24, 0))
FOG_CENTER = Vec3(0, 13.13, 2.35)
FOG_SIZE = Vec3(4.1, .45, 4.7)
FORGE_ENTRY = Vec3(0, 15.2, 1.02)
BOSS_SPAWN = Vec3(0, 27, 1.65)
SHORTCUT_CENTER = Vec3(0, 8.8, 1.7)
SHORTCUT_SIZE = Vec3(3, .45, 3.4)


def blocks() -> list[Block]:
    """Gera perímetro, ruínas, aberturas e pedestais."""
    pieces = [
        Block("solo", Vec3(0, 0, -0.5), Vec3(24, 28, 1), FLOOR),
        Block("muralha-sul", Vec3(0, -13, 1.5), Vec3(23, 0.8, 3), STONE),
        Block("muralha-oeste", Vec3(-11.5, 0, 1.85), Vec3(0.8, 26, 3.7), STONE),
        Block("muralha-leste", Vec3(11.5, 0, 1.85), Vec3(0.8, 26, 3.7), STONE),
        Block("muralha-norte-oeste", Vec3(-6.6, 13, 2.3), Vec3(9, 0.85, 4.6), STONE),
        Block("muralha-norte-leste", Vec3(6.6, 13, 2.3), Vec3(9, 0.85, 4.6), STONE),
        Block("lintel", Vec3(0, 13, 4.65), Vec3(5.9, 1.22, 0.66), TRIM),
        Block("entulho-oeste", Vec3(-5, 0.1, 0.55), Vec3(2.35, 1.25, 1.1), STONE),
        Block("entulho-leste", Vec3(4.45, 0.65, 0.77), Vec3(1.4, 2.35, 1.54), STONE),
        Block("claustro-oeste", Vec3(-5.5, 8.8, 1.7), Vec3(8, .45, 3.4), STONE),
        Block("claustro-leste", Vec3(5.5, 8.8, 1.7), Vec3(8, .45, 3.4), STONE),
        Block("forja-solo", Vec3(0, 25, -.5), Vec3(24, 24, 1), FLOOR),
        Block("forja-oeste", Vec3(-11.5, 25, 3), Vec3(.8, 24, 6), STONE),
        Block("forja-leste", Vec3(11.5, 25, 3), Vec3(.8, 24, 6), STONE),
        Block("forja-norte", Vec3(0, 37, 3), Vec3(23.8, .8, 6), STONE),
        Block("fornalha", Vec3(0, 36.2, 1.4), Vec3(5, 1.3, 2.8), BRASS),
    ]
    for i, (x, y, height) in enumerate((
        (-8.25, -4.5, 2.6), (8.25, -4.5, 3.05), (-8.25, 7.7, 4.6),
        (8.25, 7.7, 4.6), (-2.65, 12.4, 5.5), (2.65, 12.4, 5.5),
    )):
        pieces += [
            Block(f"base-{i}", Vec3(x, y, 0.27), Vec3(1.75, 1.65, 0.54), TRIM),
            Block(f"coluna-{i}", Vec3(x, y, height / 2), Vec3(1.17, 1.12, height), STONE),
            Block(f"capitel-{i}", Vec3(x, y, height), Vec3(1.58, 1.46, 0.36), TRIM),
        ]
    for side in (-1, 1):
        for y in range(-11, 13, 3):
            pieces.append(Block("ameia", Vec3(side * 11.5, y, 3.98),
                                Vec3(0.95, 1.28, 0.63), TRIM, False))
    for x in range(-9, 10, 2):
        pieces.append(Block("sulco", Vec3(x, 12.8, 4.8), Vec3(0.66, 0.96, 0.77), TRIM, False))
    for target in TARGETS:
        pieces.append(Block("pedestal", target.flat() + Vec3(0, 0, 0.12),
                            Vec3(1.55, 1.55, 0.24), TRIM))
    for fire in BRAZIERS:
        pieces.append(Block("braseiro", fire + Vec3(0, 0, 0.38),
                            Vec3(0.66, 0.66, 0.76), BRASS))
    return pieces


def enter_arena(world: World, bus: EventBus) -> None:
    """Registra alvos e publica o evento de entrada."""
    for index, position in enumerate(TARGETS):
        world.spawn(Transform(position), LockOnTarget(priority=index == 0))
    bus.publish(AreaEnteredEvent(ARENA_ID))


def nav_grid(*, fog_closed: bool = True, shortcut_closed: bool = True) -> NavGrid:
    """Constrói o grid usando as caixas físicas e uma margem para a cápsula."""
    obstacles = [
        (piece.center.x, piece.center.y, piece.size.x / 2 + .55, piece.size.y / 2 + .55)
        for piece in blocks() if piece.collision and piece.center.z + piece.size.z / 2 > .27
        and piece.center.z - piece.size.z / 2 < 1.8
    ]
    obstacles.extend((point.x, point.y, .85, .80) for point in TARGETS)
    for closed, point, dimensions in ((fog_closed, FOG_CENTER, FOG_SIZE),
                                       (shortcut_closed, SHORTCUT_CENTER, SHORTCUT_SIZE)):
        if closed:
            obstacles.append((point.x, point.y, dimensions.x / 2 + .55, dimensions.y / 2 + .55))
    origin, size = Vec3(-12, -13.5, .95), .75
    rows = []
    for y in range(68):
        row = []
        for x in range(32):
            px, py = origin.x + (x + .5) * size, origin.y + (y + .5) * size
            row.append(not any(abs(px - cx) <= half_x and abs(py - cy) <= half_y
                               for cx, cy, half_x, half_y in obstacles))
        rows.append(tuple(row))
    return NavGrid(tuple(rows), size, origin)


def enemy_spawns(count: int) -> tuple[Vec3, ...]:
    """Distribui os agentes em células livres, fora do checkpoint sul."""
    grid = nav_grid()
    preferred = (Vec3(-5, 5, .95), Vec3(4, 4, .95), Vec3(0, 10, .95))
    points = []
    for point in preferred:
        cell = grid.to_cell(point)
        if grid.walkable(cell):
            points.append(grid.to_world(cell))
    for y in range(20, 31, 3):
        for x in range(5, 28, 3):
            point = grid.to_world((x, y))
            if grid.walkable((x, y)) and all((point - other).length() > 1.5 for other in points):
                points.append(point)
    # As portas novas podem ocupar pontos preferenciais do ensaio com 20 agentes.
    if len(points) < count:
        for y in range(16, 33):
            for x in range(4, 29):
                point = grid.to_world((x, y))
                if grid.walkable((x, y)) and all((point - other).length() > 1.5 for other in points):
                    points.append(point)
                if len(points) >= count:
                    break
            if len(points) >= count:
                break
    if not 0 <= count <= min(20, len(points)):
        raise ValueError("A arena suporta de zero a vinte inimigos.")
    return tuple(points[:count])
