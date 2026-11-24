"""Câmera orbital com spring arm, colisão e enquadramento do alvo."""

import math
from dataclasses import dataclass

from vigilia.core.mathx import Vec3
from vigilia.core.protocols import IPhysicsWorld


@dataclass(frozen=True, slots=True)
class CameraPose:
    position: Vec3
    look_at: Vec3


class SpringArmCamera:
    """Encurta o braço imediatamente e suaviza a extensão ao sair de paredes."""

    def __init__(self, physics: IPhysicsWorld, sensitivity: float) -> None:
        self._physics = physics
        self._sensitivity = sensitivity
        self._yaw = 0.0
        self._pitch = math.radians(18)
        self._arm = 5.8
        self._target: Vec3 | None = None

    def look(self, mouse: tuple[float, float], stick: tuple[float, float], dt: float) -> None:
        """Integra o deslocamento do mouse e a velocidade do analógico direito."""
        if self._target is None:
            self._yaw += mouse[0] * self._sensitivity + stick[0] * dt * 2.7
            pitch = self._pitch + mouse[1] * self._sensitivity - stick[1] * dt * 1.9
            self._pitch = max(math.radians(-12), min(math.radians(62), pitch))

    def set_sensitivity(self, sensitivity: float) -> None:
        self._sensitivity = sensitivity

    def set_target(self, target: Vec3 | None) -> None:
        """Define ou limpa o ponto de atenção em lock-on."""
        self._target = target

    def axes(self, player: Vec3) -> tuple[Vec3, Vec3]:
        """Retorna eixos horizontais usados no movimento relativo à câmera."""
        forward = Vec3(math.sin(self._yaw), math.cos(self._yaw))
        if self._target is not None:
            direction = (self._target - player).flat().normalized()
            if direction.length() > 0:
                forward = direction
        return forward, Vec3(forward.y, -forward.x)

    def update(self, player: Vec3, elapsed: float) -> CameraPose:
        """Calcula a pose interpolada da câmera e testa a folga contra o cenário."""
        pivot = player + Vec3(0, 0, 0.53)
        forward, right = self.axes(player)
        look_at = pivot
        offset = forward * (-5.8 * math.cos(self._pitch)) + Vec3(0, 0, 5.8 * math.sin(self._pitch))
        if self._target is not None:
            self._yaw = math.atan2(forward.x, forward.y)
            look_at = pivot.lerp(self._target, 0.32)
            offset = forward * -5.3 + right * 0.85 + Vec3(0, 0, 1.7)

        distance = offset.length()
        hit = self._physics.sweep_sphere(pivot, pivot + offset, 0.22)
        limit = distance if hit is None else max(0.06, hit.distance - 0.07)
        extension = 1 - math.exp(-9 * max(0.0, elapsed))
        self._arm = min(limit, self._arm + (limit - self._arm) * extension)
        return CameraPose(pivot + offset.normalized() * self._arm, look_at)
