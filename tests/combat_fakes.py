"""Adaptadores geométricos mínimos para testes de domínio."""

import math
from vigilia.core.mathx import Vec3
from vigilia.core.types import VolumeRayHit


class ContactFake:
    def __init__(self) -> None:
        self.volumes = {}

    def sync(self, volumes) -> None:
        self.volumes = volumes

    def overlaps(self, source, targets) -> bool:
        if source not in self.volumes:
            return False
        start, radius = self.volumes[source]
        return any(target in self.volumes and
                   (start - self.volumes[target][0]).length() <= radius + self.volumes[target][1]
                   for target in targets)

    def raycast(self, origin, end, targets):
        direction, length = (end - origin).normalized(), (end - origin).length()
        hits = []
        for key in targets:
            if key not in self.volumes:
                continue
            center, radius = self.volumes[key]
            relative = origin - center
            projection = relative.dot(direction)
            discriminant = projection ** 2 - relative.dot(relative) + radius ** 2
            if discriminant < 0 or -projection + math.sqrt(discriminant) < 0:
                continue
            distance = max(0, -projection - math.sqrt(discriminant))
            if distance <= length:
                hits.append(VolumeRayHit(key, origin + direction * distance, distance))
        return min(hits, key=lambda hit: hit.distance) if hits else None


class PhysicsFake:
    def __init__(self) -> None:
        self.wall = None
        self.velocity = Vec3()
        self.position_value = Vec3(0, 0, 1)
        self.active = True

    def raycast(self, origin, end):
        return self.wall

    def sweep_sphere(self, origin, end, radius):
        return self.wall

    def set_velocity(self, velocity):
        self.velocity = velocity

    def position(self):
        return self.position_value

    def teleport(self, position):
        self.position_value = position

    def set_active(self, active):
        self.active = active
