"""Vetores e transformações de gameplay em coordenadas Z-up."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Vec3:
    """Vetor de três componentes independente da engine."""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def __add__(self, other: Vec3) -> Vec3:
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: Vec3) -> Vec3:
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scale: float) -> Vec3:
        return Vec3(self.x * scale, self.y * scale, self.z * scale)

    def dot(self, other: Vec3) -> float:
        """Calcula o produto escalar."""
        return self.x * other.x + self.y * other.y + self.z * other.z

    def length(self) -> float:
        """Retorna o comprimento euclidiano."""
        return math.sqrt(self.dot(self))

    def normalized(self) -> Vec3:
        """Retorna uma direção ou o vetor nulo."""
        length = self.length()
        return self * (1.0 / length) if length > 1e-8 else Vec3()

    def flat(self) -> Vec3:
        """Projeta o vetor no chão."""
        return Vec3(self.x, self.y)

    def lerp(self, other: Vec3, alpha: float) -> Vec3:
        """Interpola linearmente entre dois vetores."""
        return self + (other - self) * alpha


def lerp_angle(start: float, end: float, alpha: float) -> float:
    """Interpola o menor arco entre dois ângulos em radianos."""
    return start + ((end - start + math.pi) % math.tau - math.pi) * alpha


@dataclass(slots=True)
class Transform:
    """Posição mundial e yaw medido de +Y em direção a +X."""

    position: Vec3 = Vec3()
    yaw: float = 0.0

    def forward(self) -> Vec3:
        """Retorna a direção horizontal da pose."""
        return Vec3(math.sin(self.yaw), math.cos(self.yaw))
