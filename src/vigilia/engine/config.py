"""Capacidades detectadas ficam no adaptador, fora do arquivo de preferências."""

from panda3d.core import GraphicsWindow, WindowProperties


class ConfigAdapter:
    def __init__(self, app):
        self.app = app
        self.desktop = (app.pipe.get_display_width(), app.pipe.get_display_height())
        self.last = None

    def resolutions(self):
        width, height = self.desktop
        values = [(1280, 720), (1600, 900), (1920, 1080)]
        return tuple(value for value in values if value[0] <= width and value[1] <= height) or ((1280, 720),)

    def apply(self, config):
        signature = (config.width, config.height, config.fullscreen)
        if signature == self.last:
            return
        self.last = signature
        if isinstance(self.app.win, GraphicsWindow):
            props = WindowProperties()
            props.set_size(config.width, config.height)
            props.set_fullscreen(config.fullscreen)
            self.app.win.request_properties(props)
