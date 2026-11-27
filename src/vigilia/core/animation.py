"""Read-only presentation inputs and reusable transform interpolation."""
from dataclasses import dataclass
from typing import NamedTuple


class PoseChannels(NamedTuple):
    pitch: float = 0
    roll: float = 0
    yaw: float = 0
    height: float = 0
    torso: float = 0
    head: float = 0
    left_leg: float = 0
    right_leg: float = 0
    left_arm: float = 0
    right_arm: float = 0
    left_knee: float = 0
    right_knee: float = 0


@dataclass(frozen=True, slots=True)
class AnimationView:
    action: str = 'idle'
    progress: float | None = None
    speed: float = 0
    direction: float = 0
    profile: str = 'player'
    phase: int = 1
    paused: bool = False


def smoothstep(value: float) -> float:
    value = min(1., max(0., value))
    return value * value * (3 - 2 * value)


def interpolate_pose(a: PoseChannels, b: PoseChannels, weight: float) -> PoseChannels:
    """Angles take the shortest route; translation remains linear."""
    values = [x + (y - x) * weight for x, y in zip(a, b)]
    for index in range(3):
        delta = (b[index] - a[index] + 180) % 360 - 180
        values[index] = a[index] + delta * weight
    return PoseChannels(*values)
