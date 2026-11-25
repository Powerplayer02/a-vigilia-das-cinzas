"""Geometria procedural, materiais GLSL e apresentação da arena."""

import math
from pathlib import Path

from direct.gui.OnscreenText import OnscreenText
from direct.showbase.ShowBase import ShowBase
from panda3d.core import (
    Filename, Geom, GeomNode, GeomTriangles, GeomVertexData, GeomVertexFormat,
    GeomVertexWriter, NodePath, Shader, TextNode, LineSegs, CardMaker, TransparencyAttrib,
)

from vigilia.core.config import Config
from vigilia.core.mathx import Vec3
from vigilia.core.types import Action
from vigilia.engine.camera import CameraPose
from vigilia.engine.physics import to_point
from vigilia.engine.shadows import ContactShadows

Color = tuple[float, float, float, float]


def _unit_cube() -> NodePath:
    data = GeomVertexData("box", GeomVertexFormat.get_v3n3(), Geom.UH_static)
    vertex = GeomVertexWriter(data, "vertex")
    normal = GeomVertexWriter(data, "normal")
    triangles = GeomTriangles(Geom.UH_static)
    faces = (
        ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
        ((-1, 0, 0), (0, -1, 0), (0, 0, 1)),
        ((0, 1, 0), (-1, 0, 0), (0, 0, 1)),
        ((0, -1, 0), (1, 0, 0), (0, 0, 1)),
        ((0, 0, 1), (1, 0, 0), (0, 1, 0)),
        ((0, 0, -1), (-1, 0, 0), (0, 1, 0)),
    )
    for face, (n, u, v) in enumerate(faces):
        for s, t in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            vertex.add_data3(*(0.5 * (n[i] + s * u[i] + t * v[i]) for i in range(3)))
            normal.add_data3(*n)
        first = face * 4
        triangles.add_vertices(first, first + 1, first + 2)
        triangles.add_vertices(first, first + 2, first + 3)
    geometry = Geom(data)
    geometry.add_primitive(triangles)
    node = GeomNode("box")
    node.add_geom(geometry)
    return NodePath(node)


class ArenaRenderer:
    """Mantém apenas os nós de apresentação e aplica poses interpoladas."""

    def __init__(self, app: ShowBase, assets: Path, config: Config, *, localizer=None) -> None:
        self._app = app
        self.localizer = localizer
        app.set_background_color(.17, .207, .25)
        app.camLens.set_near_far(.08, 100)
        app.camLens.set_fov(71)
        self.root = app.render.attach_new_node("arena-visual")
        directory = assets / "shaders"
        shader = Shader.load(
            Shader.SL_GLSL, Filename.from_os_specific(str(directory / "stone.vert")),
            Filename.from_os_specific(str(directory / "stone.frag")),
        )
        self.root.set_shader(shader)
        self.root.set_shader_input("eye_pos", to_point(Vec3()))
        self.root.set_shader_input("masonry", 0.0)
        self.area_style((.17, .207, .25), (1., 1., 1.))
        self.shadows = ContactShadows(app.render, config.shadow_quality)
        self.apply_config(config)
        self.statics = self.root.attach_new_node("architecture")
        self.batch_statics = True
        self._static_shapes = []
        self._cube = _unit_cube()
        self._flames: list[NodePath] = []
        self._targets: dict[int, NodePath] = {}
        self._dummies: dict[int, NodePath] = {}
        self._enemies: dict[int, tuple[NodePath, NodePath, tuple[NodePath, ...]]] = {}
        self._tracers: list[tuple[NodePath, float]] = []
        self._combat_gear: dict[int, tuple[NodePath, NodePath, NodePath]] = {}
        self._gear_styles: dict[int, str] = {}
        self._gates: dict[str, NodePath] = {}
        self._player = self.root.attach_new_node("vigia")
        self._rig = self._player.attach_new_node("pose")
        self._limbs = self._make_humanoid(self._rig, (.40, .12, .105, 1))
        self._elapsed = 0.0
        self._stride = 0.0
        self._locked: int | None = None
        self._stain = self.root.attach_new_node("mancha-de-almas")
        self._box(self._stain, "almas", Vec3(), Vec3(.35, .35, .12), (.35, .84, 1, 1))
        self._stain.hide()
        self._pause_key = config.bindings[Action.PAUSE].upper()
        self._plate = app.aspect2d.attach_new_node("legenda")
        OnscreenText(
            parent=self._plate, text="A VIGÍLIA DAS CINZAS", pos=(0, .89),
            scale=.053, fg=(.94, .84, .67, 1), shadow=(.05, .04, .03, .9),
        )
        self._area_text = OnscreenText(
            parent=self._plate, text="P Á T I O   D A   V I G Í L I A", pos=(0, .824),
            scale=.029, fg=(.85, .77, .63, 1), shadow=(.05, .04, .03, .9),
            mayChange=True,
        )
        keys = config.bindings
        movement = " / ".join(keys[action].upper() for action in (
            Action.MOVE_FORWARD, Action.MOVE_LEFT, Action.MOVE_BACK, Action.MOVE_RIGHT,
        ))
        controls = (
            f"{movement}  Mover     {keys[Action.RUN].upper()}  Correr     "
            f"{keys[Action.ROLL].upper()}  Esquivar     {keys[Action.LOCK_ON].upper()}  Travar alvo"
        )
        OnscreenText(parent=self._plate, text=controls, pos=(0, -.906), scale=.038,
                     fg=(.98, .89, .74, 1), bg=(.05, .055, .065, .87))
        self._pause = OnscreenText(
            parent=app.aspect2d, text=f"PAUSA\n{self._pause_key}  Voltar     F10  Sair",
            pos=(0, .085), scale=.069, fg=(.98, .88, .72, 1), bg=(.05, .055, .065, .94),
        )
        self._pause.hide()
        self._combat_text = OnscreenText(
            parent=app.a2dTopLeft, text="", pos=(.06, -.12), scale=.036,
            align=TextNode.A_left, fg=(.98, .89, .74, 1), shadow=(0, 0, 0, 1),
            mayChange=True,
        )
        self._target_text = OnscreenText(
            parent=app.a2dTopRight, text="", pos=(-.06, -.12), scale=.032,
            align=TextNode.A_right, fg=(.93, .82, .70, 1), shadow=(0, 0, 0, 1),
            mayChange=True,
        )
        self._feedback = OnscreenText(
            parent=app.aspect2d, text="", pos=(0, -.71), scale=.042,
            fg=(1, .82, .42, 1), shadow=(0, 0, 0, 1), mayChange=True,
        )
        attack_help = (
            f"{keys[Action.LIGHT]}  Leve / crítico     {keys[Action.HEAVY]}  Forte (segurar)     "
            f"{keys[Action.BLOCK]}  Guarda     {keys[Action.PARRY]}  Parry\n"
            f"{keys[Action.SWAP_WEAPON]}  Trocar arma     {keys[Action.RESET_ARENA]}  Reiniciar treino     "
            f"{keys[Action.PAUSE]}  Pausa"
        )
        OnscreenText(parent=self._plate, text=attack_help, pos=(0, -.79), scale=.029,
                     fg=(.94, .87, .73, 1), shadow=(0, 0, 0, 1))
        self._boss_hud = app.aspect2d.attach_new_node("boss-hud")
        card = CardMaker("boss-bar-background")
        card.set_frame(-.77, .77, -.635, -.595)
        self._boss_hud.attach_new_node(card.generate()).set_color(.07, .055, .045, .95)
        self._boss_bar = self._boss_hud.attach_new_node("boss-bar")
        self._boss_bar.set_pos(-.75, 0, -.63)
        card = CardMaker("boss-health")
        card.set_frame(0, 1.5, 0, .03)
        self._boss_bar.attach_new_node(card.generate()).set_color(.65, .14, .055, 1)
        self._boss_name = OnscreenText(parent=self._boss_hud, text="", pos=(0, -.57), scale=.043,
                                      fg=(.99, .85, .62, 1), shadow=(0, 0, 0, 1), mayChange=True)
        self._boss_intro = OnscreenText(parent=app.aspect2d, text="", pos=(0, .12), scale=.085,
                                       fg=(1, .85, .59, 1), shadow=(0, 0, 0, 1), mayChange=True)
        card = CardMaker("intro-fade")
        card.set_frame(-1, 1, -1, 1)
        self._boss_fade = app.render2d.attach_new_node(card.generate())
        self._boss_fade.set_transparency(TransparencyAttrib.M_alpha)
        self._boss_fade.set_color(0, 0, 0, .2)
        self._boss_fade.set_bin("fixed", -10)
        line = LineSegs("forge-fire-ring")
        line.set_color(1, .48, .08, 1)
        line.set_thickness(4)
        for index in range(65):
            angle = math.tau * index / 64
            point = (math.cos(angle), math.sin(angle), 0)
            line.move_to(*point) if index == 0 else line.draw_to(*point)
        self._boss_ring = app.render.attach_new_node(line.create())
        self._boss_ring.set_light_off()
        for node in (self._boss_hud, self._boss_intro, self._boss_fade, self._boss_ring):
            node.hide()

    def _box(self, parent: NodePath, name: str, center: Vec3, size: Vec3, color: Color) -> NodePath:
        box = self._cube.copy_to(parent)
        box.set_name(name)
        box.set_pos(to_point(center))
        box.set_scale(size.x, size.y, size.z)
        box.set_color_scale(*color)
        return box

    def apply_config(self, config):
        self._app.camLens.set_near_far(.08, config.draw_distance)
        self.root.set_shader_input("draw_distance", float(config.draw_distance))
        self.shadows.configure(config.shadow_quality)

    def set_legacy_hud(self, enabled: bool, *, font=None) -> None:
        """Mantém a apresentação antiga apenas para o ensaio A/B do HUD."""
        self._legacy_hud = enabled
        if not enabled:
            self._boss_intro.setScale(44 / 360)
            if font is not None:
                self._boss_intro.textNode.set_font(font)
        for node in (self._plate, self._combat_text, self._target_text, self._feedback):
            node.show() if enabled else node.hide()

    def block(self, name: str, center: Vec3, size: Vec3, color: Color) -> None:
        """Acrescenta uma peça visível com a mesma caixa da física."""
        masonry = 0. if name.startswith(("water", "boardwalk", "reed", "trunk")) else .92
        if self.batch_statics:
            self._static_shapes.append((center, size, tuple(color), masonry))
        else:
            node = self._box(self.statics, name, center, size, color)
            node.set_shader_input("masonry", masonry)

    def finish_scene(self):
        """Mescla caixas por material sem alterar colisões ou cores do shader."""
        groups = {}
        for center, size, color, masonry in self._static_shapes:
            groups.setdefault((color, masonry), []).append((center, size))
        faces = (((1,0,0),(0,1,0),(0,0,1)), ((-1,0,0),(0,-1,0),(0,0,1)),
            ((0,1,0),(-1,0,0),(0,0,1)), ((0,-1,0),(1,0,0),(0,0,1)),
            ((0,0,1),(1,0,0),(0,1,0)), ((0,0,-1),(-1,0,0),(0,1,0)))
        for (color, masonry), shapes in groups.items():
            data = GeomVertexData("static-batch", GeomVertexFormat.get_v3n3(), Geom.UH_static)
            vertex, normal = GeomVertexWriter(data, "vertex"), GeomVertexWriter(data, "normal")
            triangles = GeomTriangles(Geom.UH_static)
            for index, (center, size) in enumerate(shapes):
                for face, (n, u, v) in enumerate(faces):
                    for s, t in ((-1,-1),(1,-1),(1,1),(-1,1)):
                        local = tuple(.5 * (n[i] + s*u[i] + t*v[i]) for i in range(3))
                        vertex.add_data3(center.x + size.x*local[0], center.y + size.y*local[1], center.z + size.z*local[2])
                        normal.add_data3(*n)
                    first = index * 24 + face * 4
                    triangles.add_vertices(first, first+1, first+2)
                    triangles.add_vertices(first, first+2, first+3)
            geom = Geom(data)
            geom.add_primitive(triangles)
            node = GeomNode("static-batch")
            node.add_geom(geom)
            path = self.statics.attach_new_node(node)
            path.set_color_scale(*color)
            path.set_shader_input("masonry", masonry)
        self._static_shapes.clear()

    def clear_scene(self):
        self.statics.remove_node()
        self.statics = self.root.attach_new_node("architecture")
        self._static_shapes.clear()
        for root in self._flames:
            root.remove_node()
        self._flames.clear()
        for root in self._gates.values():
            root.remove_node()
        self._gates.clear()
        for identity in tuple(self._targets):
            self._targets.pop(identity).remove_node()
        for root in self._dummies.values():
            root.remove_node()
        self._dummies.clear()
        for root, _, _ in self._enemies.values():
            root.remove_node()
        self._enemies.clear()
        for identity, gear in list(self._combat_gear.items()):
            if identity != 0:
                for node in gear:
                    node.remove_node()
                self._combat_gear.pop(identity)
                self._gear_styles.pop(identity, None)
        for root in self.shadows.nodes.values():
            root.remove_node()
        self.shadows.nodes.clear()

    def area_style(self, fog, light):
        self._app.set_background_color(*fog)
        self.root.set_shader_input("area_fog", (*fog, 1.))
        self.root.set_shader_input("area_light", (*light, 1.))

    def passage(self, identity, position, *, locked=False):
        color = (.20, .42, .48, 1) if not locked else (.44, .24, .12, 1)
        for side in (-1, 1):
            self.block(identity, position + Vec3(side * 1.2, 0, .7), Vec3(.25, .55, 3.3), color)
        self.block(identity, position + Vec3(0, 0, 2.3), Vec3(2.8, .6, .35), color)

    def brazier(self, position: Vec3) -> None:
        """Acrescenta uma chama procedural sem custo de luz dinâmica."""
        root = self.root.attach_new_node("chama")
        root.set_pos(to_point(position + Vec3(0, 0, .91)))
        for width, height, yaw, tint in (
            (.41, .54, 18, (1, .43, .13, 1)),
            (.29, .56, 58, (1, .68, .28, 1)),
            (.16, .63, 6, (1, .88, .52, 1)),
        ):
            flame = self._box(root, "fogo", Vec3(0, 0, .04), Vec3(width, width, height), tint)
            flame.set_hpr(yaw, 18, 18)
        self._flames.append(root)

    def target(self, identifier: int, position: Vec3) -> None:
        """Desenha o manequim e registra seu marcador de lock-on."""
        target = self.root.attach_new_node("manequim")
        target.set_pos(to_point(position))
        target.set_h(180)
        wood = (.45, .30, .19, 1)
        self._box(target, "poste", Vec3(0, 0, -.18), Vec3(.19, .22, 1.14), wood)
        self._box(target, "bracos", Vec3(0, 0, .29), Vec3(1.13, .18, .14), wood)
        self._box(target, "torso", Vec3(0, 0, .16), Vec3(.51, .39, .61), (.52, .39, .30, 1))
        self._box(target, "elmo", Vec3(0, 0, .62), Vec3(.33, .33, .32), (.58, .42, .29, 1))
        self._box(target, "face", Vec3(0, .17, .63), Vec3(.24, .02, .07), (.17, .1, .08, 1))
        marker = target.attach_new_node("alvo-travado")
        marker.set_pos(0, 0, 1.12)
        diamond = self._box(marker, "losango", Vec3(), Vec3(.12, .12, .12), (.97, .80, .40, 1))
        diamond.set_hpr(45, 45, 0)
        marker.hide()
        self._targets[identifier] = marker
        self._dummies[identifier] = target

    def combat_info(self, player: str, targets: str, feedback: str) -> None:
        """Apresenta vida, estamina e resultados do treino."""
        for widget, value in ((self._combat_text, player), (self._target_text, targets), (self._feedback, feedback)):
            if widget.getText() != value:
                widget.setText(value)

    def bloodstain(self, position: Vec3 | None) -> None:
        """Mostra o ponto recuperável com as almas da última morte."""
        if position is None:
            self._stain.hide()
        else:
            self._stain.set_pos(to_point(position + Vec3(0, 0, -.65)))
            self._stain.show()

    def combat_pose(self, identifier: int, bones: dict[str, Vec3], *,
                    axe: bool, alive: bool, hit: bool, telegraph: bool, ranged: bool = False,
                    knocked_down: bool = False, weapon_style: str = "", shield_equipped: bool = True) -> None:
        """Desenha a arma e o escudo nos mesmos pontos usados pelas consultas Bullet."""
        if identifier not in self._combat_gear:
            weapon = self.root.attach_new_node("arma-articulada")
            self._box(weapon, "lamina", Vec3(), Vec3(.065, 1, .08), (.75, .78, .77, 1))
            head = self._box(weapon, "cabeca-machado", Vec3(0, .38, 0),
                             Vec3(.46, .28, .13), (.55, .58, .59, 1))
            shield = self._box(self.root, "guarda", Vec3(), Vec3(.43, .12, .57), (.45, .16, .12, 1))
            self._combat_gear[identifier] = weapon, head, shield
        weapon, head, shield = self._combat_gear[identifier]
        self.shadows.pose(identifier, bones["body_center"], alive, 1.8 if "forge" in weapon_style else 1.)
        if self._gear_styles.get(identifier) != weapon_style:
            self._gear_styles[identifier] = weapon_style
            head.set_scale(.4, .8, 1.5) if weapon_style == "mace" else head.set_scale(.4, .7, 1.8) if weapon_style == "staff" else head.set_scale(1)
            head.set_color_scale(.25, .65, 1, 1) if weapon_style == "staff" else head.set_color_scale(1, 1, 1, 1)
            weapon.get_child(0).set_color_scale(.5, .32, .16, 1) if weapon_style == "staff" else weapon.get_child(0).set_color_scale(1, 1, 1, 1)
        if not alive:
            weapon.hide()
            shield.hide()
        else:
            weapon.show()
            shield.show()
            grip, tip = bones["grip"], bones["blade_tip"]
            weapon.set_pos(to_point(grip.lerp(tip, .5)))
            weapon.look_at(to_point(tip))
            weapon.set_scale(1, (tip - grip).length(), 1)
            head.show() if axe or ranged or weapon_style in ("staff", "mace") else head.hide()
            shield.set_pos(to_point(bones["shield"]))
            if identifier in self._enemies or not shield_equipped:
                shield.hide()
            else:
                shield.set_h(self._player.get_h() if identifier not in self._dummies
                             else self._dummies[identifier].get_h())
        if identifier in self._dummies:
            dummy = self._dummies[identifier]
            dummy.set_color_scale((1.8, .72, .5, 1) if hit else
                                  (1.7, 1.25, .6, 1) if telegraph else (1, 1, 1, 1))
            dummy.set_p(78 if not alive else 0)
        elif identifier in self._enemies:
            root, rig, limbs = self._enemies[identifier]
            root.set_color_scale((1.8, .72, .5, 1) if hit else
                                 (1.6, 1.25, .65, 1) if telegraph else (1, 1, 1, 1))
            rig.set_p(0 if alive else 82)
            if alive:
                for limb, bone in ((limbs[0], "arm_left"), (limbs[2], "grip")):
                    limb.look_at(self.root, to_point(bones[bone]))
                    limb.set_p(limb, 90)
        else:
            self._player.set_color_scale((1.7, .6, .5, 1) if hit else (1, 1, 1, 1))
            for limb, bone in ((self._limbs[0], "arm_left"), (self._limbs[2], "grip")):
                limb.look_at(self.root, to_point(bones[bone]))
                limb.set_p(limb, 90)
            if not alive:
                self._rig.set_p(82)
            elif knocked_down:
                self._rig.set_p(78)

    def _make_humanoid(self, rig: NodePath, cloth: Color) -> tuple[NodePath, ...]:
        iron = (.39, .46, .49, 1)
        edge = (.62, .64, .59, 1)
        leather = (.22, .18, .17, 1)
        self._box(rig, "peitoral", Vec3(0, 0, .22), Vec3(.56, .38, .55), iron)
        self._box(rig, "cintura", Vec3(0, 0, -.07), Vec3(.51, .34, .15), leather)
        self._box(rig, "elmo", Vec3(0, 0, .67), Vec3(.37, .35, .34), edge)
        self._box(rig, "viseira", Vec3(0, .178, .68), Vec3(.29, .025, .071), leather)
        self._box(rig, "capa", Vec3(0, -.231, .04), Vec3(.49, .078, .82), cloth)
        limbs = []
        for side in (-1, 1):
            arm = rig.attach_new_node("braco")
            arm.set_pos(side * .36, 0, .40)
            self._box(arm, "ombreira", Vec3(0, 0, -.055), Vec3(.24, .36, .22), iron)
            self._box(arm, "manopla", Vec3(0, 0, -.29), Vec3(.15, .22, .41), edge)
            leg = rig.attach_new_node("perna")
            leg.set_pos(side * .147, 0, -.09)
            self._box(leg, "greva", Vec3(0, 0, -.331), Vec3(.195, .229, .69), iron)
            self._box(leg, "bota", Vec3(0, .074, -.70), Vec3(.2, .34, .155), leather)
            limbs.extend((arm, leg))
        return tuple(limbs)

    def enemy(self, identifier: int, position: Vec3, tint: Color, *, scale: float = 1) -> None:
        """Cria um rig de baixa contagem de polígonos para um agente."""
        root = self.root.attach_new_node("adversario")
        root.set_pos(to_point(position))
        root.set_scale(scale)
        rig = root.attach_new_node("pose")
        limbs = self._make_humanoid(rig, tint)
        self._enemies[identifier] = root, rig, limbs
        marker = root.attach_new_node("alvo-travado")
        self._box(marker, "marca", Vec3(0, 0, 1.1), Vec3(.13, .13, .13), (.97, .80, .40, 1))
        marker.hide()
        self._targets[identifier] = marker

    def gate(self, identifier: str, position: Vec3, size: Vec3, *, fog: bool = False) -> None:
        color = (.68, .72, .78, .63) if fog else (.29, .17, .09, 1)
        gate = self._box(self.root, identifier, position, size, color)
        if fog:
            gate.set_transparency(TransparencyAttrib.M_alpha)
        self._gates[identifier] = gate

    def gate_open(self, identifier: str, opened: bool) -> None:
        gate = self._gates[identifier]
        gate.hide() if opened else gate.show()

    def hazard(self, position, visible, active):
        if not hasattr(self, "_vent_marker"):
            lines = LineSegs("ember-vent")
            lines.set_thickness(4)
            for i in range(65):
                angle = i * math.tau / 64
                point = (2.4 * math.cos(angle), 2.4 * math.sin(angle), 0)
                lines.move_to(*point) if i == 0 else lines.draw_to(*point)
            self._vent_marker = self._app.render.attach_new_node(lines.create())
            self._vent_marker.set_light_off()
        self._vent_marker.set_pos(position.x, position.y, .07)
        self._vent_marker.set_color_scale(1, .10 if active else .65, .02, 1)
        self._vent_marker.show() if visible else self._vent_marker.hide()

    def boss_color(self, color):
        self._boss_ring.set_color(*color)

    def boss_info(self, name: str, hp: float, maximum: float, phase: int, visible: bool,
                  intro: float, transitioning: bool, position: Vec3, radius: float, phase_caption="") -> None:
        self._boss_hud.show() if visible and self._legacy_hud else self._boss_hud.hide()
        self._boss_bar.set_sx(max(.0001, hp / max(1, maximum)))
        caption = f"{name}  •  Fase {phase}"
        if self._boss_name.getText() != caption:
            self._boss_name.setText(caption)
        if visible and (intro > 0 or transitioning):
            caption = (phase_caption or self.localizer.t("boss.phase2")) if transitioning else name.upper()
            if self._boss_intro.getText() != caption:
                self._boss_intro.setText(caption)
            self._boss_intro.show()
            self._boss_fade.show()
        else:
            self._boss_intro.hide()
            self._boss_fade.hide()
        if visible and radius > 0:
            self._boss_ring.set_pos(position.x, position.y, .05)
            self._boss_ring.set_scale(radius, radius, 1)
            self._boss_ring.show()
        else:
            self._boss_ring.hide()

    def enemy_motion(self, identifier: int, position: Vec3, yaw: float, speed: float) -> None:
        root, rig, limbs = self._enemies[identifier]
        root.set_pos(to_point(position))
        root.set_h(-math.degrees(yaw))
        gait = math.sin(self._elapsed * speed * 4 + identifier) * min(1, speed / 3) * 33
        limbs[1].set_p(gait)
        limbs[3].set_p(-gait)

    def tracer(self, origin: Vec3, end: Vec3, *, color=(1, .65, .24, 1)) -> None:
        """Mostra o trajeto instantâneo da besta por um intervalo curto."""
        line = LineSegs()
        line.set_color(*color)
        line.set_thickness(2)
        line.move_to(to_point(origin))
        line.draw_to(to_point(end))
        node = self._app.render.attach_new_node(line.create())
        self._tracers.append((node, self._elapsed + .14))

    def prepare_agile_visuals(self):
        if not hasattr(self, "_dash_trails"):
            self._dash_trails = []
            for index in range(16):
                node = self._box(self.root, f"dash-trail-{index}", Vec3(), Vec3(.5, .35, 1.55), (.2, .8, 1, .22))
                node.set_transparency(TransparencyAttrib.M_alpha)
                node.set_depth_write(False)
                node.hide()
                self._dash_trails.append([node, 0.])
        if not hasattr(self, "_slam_ring"):
            line = LineSegs('slam-wave')
            line.set_thickness(3)
            line.set_color(1, .7, .3, .9)
            for index in range(49):
                angle = index * math.tau / 48
                point = (math.cos(angle), math.sin(angle), 0)
                line.move_to(*point) if index == 0 else line.draw_to(*point)
            self._slam_ring = self.root.attach_new_node(line.create())
            self._slam_ring.set_shader_off()
            self._slam_ring.set_light_off()
            self._slam_ring.set_transparency(TransparencyAttrib.M_alpha)
            self._slam_ring.set_depth_write(False)
            self._slam_ring.hide()
            self._slam_expiry, self._slam_radius = 0., 0.

    def slam_wave(self, position, radius):
        self.prepare_agile_visuals()
        self._slam_ring.set_pos(to_point(position + Vec3(0, 0, .04)))
        self._slam_expiry, self._slam_radius = self._elapsed + .3, radius
        self._slam_ring.show()

    def dash_trail(self, position):
        self.prepare_agile_visuals()
        slot = min(self._dash_trails, key=lambda item: item[1])
        slot[0].set_pos(to_point(position))
        slot[0].show()
        slot[1] = self._elapsed + .25

    def set_player_crouched(self, enabled):
        self._player_crouched = enabled

    def set_player_air_state(self, state):
        self._player_air_state = state

    def draw(self, camera: CameraPose, player: Vec3, yaw: float, speed: float,
             dodge: float, rolling: bool, locked: int | None, paused: bool, dt: float) -> None:
        """Atualiza câmera, animações de prévia e informações de controle."""
        self._app.camera.set_pos(to_point(camera.position))
        self._app.camera.look_at(to_point(camera.look_at))
        area_name = "F O R N A L H A   D O   V I G I A" if player.y >= 14 else "P Á T I O   D A   V I G Í L I A"
        if self._area_text.getText() != area_name:
            self._area_text.setText(area_name)
        self.root.set_shader_input("eye_pos", to_point(camera.position))
        self._player.set_pos(to_point(player))
        self._player.set_h(-math.degrees(yaw))
        self._stride += dt * speed * 3.2
        gait = math.sin(self._stride) * min(1.0, speed / 4.7) * 35
        for index, limb in enumerate(self._limbs):
            limb.set_p(gait * (1 if index in (0, 3) else -1) if not dodge else 0)
        self._rig.set_p(-360 * dodge if rolling else 17 * math.sin(math.pi * dodge))
        if getattr(self, '_player_air_state', '') == 'slamming':
            self._rig.set_p(25)
        crouched = getattr(self, "_player_crouched", False)
        self._rig.set_sz(.5 if crouched else 1)
        self._rig.set_z(-.22 * math.sin(math.pi * dodge) - (.445 if crouched else 0))

        self._elapsed += dt
        if hasattr(self, '_slam_ring'):
            fraction = max(0., min(1., 1 - (self._slam_expiry - self._elapsed) / .3))
            self._slam_ring.set_scale(self._slam_radius * (.2 + .8 * fraction))
            self._slam_ring.set_color_scale(1, 1, 1, 1 - fraction)
            if self._elapsed >= self._slam_expiry:
                self._slam_ring.hide()
        if hasattr(self, "_dash_trails"):
            for node, expiry in self._dash_trails:
                if expiry <= self._elapsed:
                    node.hide()
        retained = []
        for tracer, expiry in self._tracers:
            if expiry < self._elapsed:
                tracer.remove_node()
            else:
                retained.append((tracer, expiry))
        self._tracers = retained
        for index, flame in enumerate(self._flames):
            flame.set_h(self._elapsed * 65 + index * 27)
            flame.set_sz(1 + .13 * math.sin(self._elapsed * 9 + index))
        if locked != self._locked:
            if self._locked is not None:
                self._targets[self._locked].hide()
            if locked is not None:
                self._targets[locked].show()
            self._locked = locked
        self._pause.show() if paused and self._legacy_hud else self._pause.hide()
