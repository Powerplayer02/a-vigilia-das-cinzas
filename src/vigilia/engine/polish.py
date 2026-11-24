"""Fade e shake de apresentação sem alterar transformações ECS ou colisões."""

from dataclasses import replace
import math
from panda3d.core import CardMaker, TransparencyAttrib
from vigilia.core.mathx import Vec3


class PresentationPolish:
    def __init__(self, app):
        self.app = app
        card = CardMaker("transition-fade")
        card.set_frame(-1, 1, -1, 1)
        self.overlay = app.render2d.attach_new_node(card.generate())
        self.overlay.set_bin("fixed", 90)
        self.overlay.set_depth_test(False)
        self.overlay.set_depth_write(False)
        self.overlay.set_transparency(TransparencyAttrib.M_alpha)
        self.overlay.hide()
        self.age, self.duration, self.hold = 0., 0., False
        self.covered = False
        self.shake_frames = 0
        self.shake_pixels = 0.
        self.strength = 1.

    def set_strength(self, value):
        self.strength = max(0., min(1., value))
        if not self.strength:
            self.shake_frames = 0

    def fade(self, seconds, *, hold=False, immediate=False):
        self.age, self.duration, self.hold, self.covered = 0., seconds, hold, immediate
        self.overlay.show()
        self.overlay.set_color(0, 0, 0, 1 if immediate else 0)

    def reveal(self, seconds=.15):
        self.fade(seconds, immediate=True)

    def cover_now(self):
        """Apresenta o preto antes de começar uma operação síncrona de checkpoint."""
        self.fade(.15, hold=True, immediate=True)
        self.app.graphicsEngine.render_frame()

    def shake(self, frames=2, pixels=3):
        self.shake_frames, self.shake_pixels = (frames if self.strength else 0), pixels

    def reset(self):
        self.age = self.duration = 0.
        self.hold = self.covered = False
        self.shake_frames = 0
        self.overlay.hide()

    def update(self, pose, dt, *, paused=False):
        if paused:
            self.overlay.hide()
            return pose
        if self.duration:
            self.overlay.show()
            self.age += dt
            fraction = min(1., self.age / self.duration)
            alpha = 1 - fraction if self.covered and not self.hold else fraction
            self.overlay.set_color(0, 0, 0, alpha)
            if fraction == 1 and not self.hold:
                self.overlay.hide()
                self.duration = 0.
        if self.shake_frames and dt > 0:
            self.shake_frames -= 1
            # Converte pixels em distância à profundidade do foco, independente da resolução.
            distance = (pose.look_at - pose.position).length()
            units = 2 * distance * math.tan(math.radians(71 / 2)) * self.shake_pixels * self.strength / max(1, self.app.win.get_x_size())
            offset = Vec3(units * (1 if self.shake_frames % 2 else -1), 0, units * .35)
            return replace(pose, position=pose.position + offset, look_at=pose.look_at + offset)
        return pose
