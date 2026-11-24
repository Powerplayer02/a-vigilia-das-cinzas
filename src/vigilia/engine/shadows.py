"""Sombras de contato procedurais: qualidade muda suavidade e tesselação."""

import math
from panda3d.core import Geom, GeomNode, GeomTriangles, GeomVertexData, GeomVertexFormat, GeomVertexWriter, NodePath, TransparencyAttrib


def disc(quality):
    segments, rings = {"low": (8, 1), "medium": (16, 2), "high": (32, 4)}[quality]
    data = GeomVertexData("contact-shadow", GeomVertexFormat.get_v3c4(), Geom.UH_static)
    vertex, color = GeomVertexWriter(data, "vertex"), GeomVertexWriter(data, "color")
    triangles = GeomTriangles(Geom.UH_static)
    for ring in range(rings + 1):
        radius = ring / rings
        alpha = .32 * (1 - radius) if rings > 1 else .25 if ring == 0 else 0
        for point in range(segments):
            angle = point * math.tau / segments
            vertex.add_data3(math.cos(angle) * radius, math.sin(angle) * radius, 0)
            color.add_data4(0, 0, 0, alpha)
    for ring in range(rings):
        for point in range(segments):
            a, b = ring * segments + point, ring * segments + (point + 1) % segments
            triangles.add_vertices(a, a + segments, b + segments)
            triangles.add_vertices(a, b + segments, b)
    geometry = Geom(data)
    geometry.add_primitive(triangles)
    node = GeomNode("contact-shadow")
    node.add_geom(geometry)
    return NodePath(node)


class ContactShadows:
    def __init__(self, parent, quality):
        self.root = parent.attach_new_node("contact-shadows")
        self.root.set_shader_off()
        self.root.set_light_off()
        self.root.set_depth_write(False)
        self.root.set_transparency(TransparencyAttrib.M_alpha)
        self.nodes, self.meshes, self.quality = {}, {}, None
        self.configure(quality)

    def configure(self, quality):
        if quality == self.quality:
            return
        self.quality = quality
        if quality == "off":
            self.root.hide()
            return
        self.root.show()
        if quality not in self.meshes:
            self.meshes[quality] = disc(quality)
        for node in self.nodes.values():
            node.get_children().detach()
            self.meshes[quality].instance_to(node)

    def pose(self, identity, point, alive, scale=1.):
        if identity not in self.nodes:
            node = self.root.attach_new_node(f"shadow-{identity}")
            self.nodes[identity] = node
            if self.quality != "off":
                self.meshes[self.quality].instance_to(node)
        node = self.nodes[identity]
        node.set_pos(point.x, point.y, .025)
        node.set_scale(.65 * scale, .48 * scale, 1)
        node.show() if alive else node.hide()
