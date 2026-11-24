from types import SimpleNamespace
from panda3d.core import NodePath
from vigilia.core.mathx import Vec3
from vigilia.engine.camera import CameraPose
from vigilia.engine.polish import PresentationPolish


def effect():
    app = SimpleNamespace(render2d=NodePath("overlay"), win=SimpleNamespace(get_x_size=lambda: 1280))
    return PresentationPolish(app)


def test_death_fade_holds_until_respawn_reveal():
    polish = effect()
    pose = CameraPose(Vec3(0, -5), Vec3())
    polish.fade(.15, hold=True)
    polish.update(pose, .15)
    assert polish.overlay.get_color()[3] == 1
    polish.update(pose, 1)
    assert not polish.overlay.is_hidden()
    polish.reveal(.15)
    polish.update(pose, .15)
    assert polish.overlay.is_hidden()


def test_fog_is_covered_immediately_and_pause_menu_remains_visible():
    polish = effect()
    pose = CameraPose(Vec3(0, -5), Vec3())
    polish.fade(.3, immediate=True)
    assert polish.overlay.get_color()[3] == 1
    polish.update(pose, 1, paused=True)
    assert polish.overlay.is_hidden() and polish.age == 0
    polish.update(pose, .1)
    assert not polish.overlay.is_hidden()
    polish.update(pose, .2)
    assert polish.overlay.is_hidden()


def test_shake_only_affects_returned_camera_and_freezes_on_pause():
    polish = effect()
    pose = CameraPose(Vec3(0, -5), Vec3())
    polish.shake(2, 3)
    assert polish.update(pose, 1, paused=True) == pose and polish.shake_frames == 2
    result = polish.update(pose, 1 / 60)
    assert result != pose and pose.position == Vec3(0, -5)
    assert result.look_at - pose.look_at == result.position - pose.position
    polish.update(pose, 1 / 60)
    assert polish.update(pose, 1 / 60) == pose


def test_switching_character_resets_death_cover_and_camera_shake():
    polish = effect()
    polish.fade(.15, hold=True, immediate=True)
    polish.shake(8, 5)
    polish.reset()
    assert polish.overlay.is_hidden() and polish.duration == 0 and polish.shake_frames == 0
