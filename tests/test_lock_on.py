"""Prioridade por cone e percurso entre quatro alvos."""

from vigilia.core.mathx import Vec3
from vigilia.player.lock_on import TargetCandidate, select_target, cycle_target


def test_camera_alignment_wins_inside_sixty_degree_cone() -> None:
    candidates = [TargetCandidate(1, Vec3(0, 10)), TargetCandidate(2, Vec3(2, 2))]
    assert select_target(candidates, Vec3(), Vec3(0, 1)) == 1
    assert select_target(candidates[1:], Vec3(), Vec3(0, 1)) == 2


def test_directional_switch_visits_dummy_and_three_enemies() -> None:
    candidates = [TargetCandidate(index, Vec3(x, y)) for index, (x, y) in enumerate(
        ((0, 8), (-2, 6), (3, 6), (4, 3)),
    )]
    current, visited = 0, {0}
    for _ in range(4):
        current = cycle_target(candidates, current, Vec3(), Vec3(0, 1), 1)
        visited.add(current)
    assert visited == {0, 1, 2, 3}
    assert current == 0
