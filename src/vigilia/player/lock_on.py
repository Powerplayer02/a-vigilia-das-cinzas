"""Seleção e troca de alvos por alinhamento e posição relativa à câmera."""

import math
from dataclasses import dataclass

from vigilia.core.mathx import Vec3


@dataclass(frozen=True, slots=True)
class TargetCandidate:
    id: int
    position: Vec3


def select_target(candidates: list[TargetCandidate], origin: Vec3, forward: Vec3) -> int | None:
    """Prioriza alinhamento em um cone total de 60 graus e depois distância."""
    if not candidates:
        return None
    aligned = [candidate for candidate in candidates
               if (candidate.position - origin).flat().normalized().dot(forward) >= math.cos(math.pi / 6)]
    if aligned:
        return min(aligned, key=lambda candidate: (
            -(candidate.position - origin).flat().normalized().dot(forward),
            (candidate.position - origin).length(), candidate.id,
        )).id
    return min(candidates, key=lambda candidate: ((candidate.position - origin).length(), candidate.id)).id


def cycle_target(candidates: list[TargetCandidate], current: int, origin: Vec3,
                 forward: Vec3, direction: int) -> int | None:
    """Percorre os alvos visíveis da esquerda para a direita e dá a volta."""
    if not candidates:
        return None
    right = Vec3(forward.y, -forward.x)
    ordered = sorted(candidates, key=lambda candidate: (
        math.atan2((candidate.position - origin).dot(right), (candidate.position - origin).dot(forward)),
        candidate.id,
    ))
    ids = [candidate.id for candidate in ordered]
    index = ids.index(current) if current in ids else 0
    return ids[(index + direction) % len(ids)]
