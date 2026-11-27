"""Original vector-drawn UI sprites packed in one mipmapped RGBA texture.

No display, font or external art is needed to build the deterministic fallback.
Cells have extruded gutters; nine-slice frames preserve corner proportions.
"""

import hashlib
import json
from pathlib import Path
import struct
import zlib

import numpy as np
from panda3d.core import (Filename, Texture, Geom, GeomNode, GeomVertexData,
    GeomVertexFormat, GeomVertexWriter, GeomTriangles, TransparencyAttrib)

from vigilia.core.palette import PALETTE

REVISION, SIZE, CELL, GUTTER = 1, 1024, 128, 8
NAMES = ("panel", "button", "ember", "sword", "axe", "katana", "staff", "mace",
    "shield", "helm", "armor", "ring", "flask", "shard", "heart", "stamina",
    "soul", "bleed", "poison", "frost", "curse", "healing", "spell", "map",
    "bonfire", "player", "settings", "volume", "controls", "save", "exit",
    "back", "confirm", "chevron", "levels", "credits")


class Ink:
    def __init__(self, palette):
        self.pixels = np.zeros((224, 224, 4), dtype=np.uint8)
        self.y, self.x = np.mgrid[:224, :224] / 2.24 + .5 / 2.24
        self.palette = palette

    def paint(self, mask, color="ink"):
        self.pixels[mask] = np.rint(np.array(self.palette[color]) * 255).astype(np.uint8)

    def line(self, points, width=4, color="ink", closed=False):
        if closed:
            points = [*points, points[0]]
        for (a, b), (c, d) in zip(points, points[1:]):
            dx, dy = c-a, d-b
            t = np.clip(((self.x-a)*dx + (self.y-b)*dy) / max(.0001, dx*dx+dy*dy), 0, 1)
            self.paint((self.x-a-t*dx)**2 + (self.y-b-t*dy)**2 <= (width/2)**2, color)

    def polygon(self, points, color="ink"):
        mask = np.zeros(self.x.shape, dtype=bool)
        for (a,b),(c,d) in zip(points, (*points[1:], points[0])):
            if b == d:
                continue
            mask ^= ((b > self.y) != (d > self.y)) & (self.x < (c-a)*(self.y-b)/(d-b)+a)
        self.paint(mask, color)

    def circle(self, x, y, radius, color="ink", width=None):
        distance = np.sqrt((self.x-x)**2+(self.y-y)**2)
        self.paint(distance <= radius if width is None else abs(distance-radius) <= width/2, color)


def draw_icon(name, palette=PALETTE):
    p = Ink(palette)
    if name in ("panel", "button"):
        p.line([(5,20),(5,5),(20,5)], 1.2, "border")
        p.line([(80,5),(95,5),(95,20)], 1.2, "border")
        p.line([(95,80),(95,95),(80,95)], 1.2, "border")
        p.line([(20,95),(5,95),(5,80)], 1.2, "border")
        p.line([(20,5),(80,5)], .6, "border")
        p.line([(20,95),(80,95)], .6, "border")
        p.line([(5,20),(5,80)], .6, "border")
        p.line([(95,20),(95,80)], .6, "border")
        for x,y in ((5,5),(95,5),(5,95),(95,95)):
            p.polygon([(x,y-2),(x+2,y),(x,y+2),(x-2,y)], "gold")
    elif name in ("ember", "bonfire", "soul", "spell"):
        if name == "ember":
            p.circle(50,50,43,"border",1)
            p.line([(50,3),(50,12)],2,"gold")
            p.line([(50,88),(50,97)],2,"gold")
        p.polygon([(48,14),(67,37),(62,48),(77,40),(76,64),(65,78),(47,84),(27,73),(23,58),(33,34),(35,54),(44,45)], "gold")
        p.polygon([(50,44),(60,62),(55,75),(42,72),(38,62)], "ink")
        if name == "bonfire":
            p.line([(23,89),(77,83)],5,"border"); p.line([(23,82),(77,90)],5,"border")
        if name == "spell":
            p.line([(16,23),(10,32),(16,41)],2,"mana"); p.line([(85,53),(91,62),(85,71)],2,"mana")
    elif name in ("sword", "katana", "staff", "mace", "axe"):
        p.line([(27,81),(64,28)],6,"border")
        p.line([(22,87),(34,70)],6,"gold")
        if name == "sword":
            p.polygon([(38,62),(65,18),(78,12),(74,30),(48,69)])
            p.line([(28,55),(59,76)],5,"gold")
        elif name == "katana":
            p.line([(39,64),(52,47),(65,27),(70,10)],7)
            p.line([(32,59),(54,73)],4,"gold")
        elif name == "axe":
            p.polygon([(55,23),(80,19),(85,38),(68,51),(58,44),(43,40)],"ink")
        elif name == "mace":
            p.polygon([(53,16),(71,13),(83,29),(76,45),(57,44),(46,29)])
            p.line([(53,16),(76,45)],3,"gold")
        else:
            p.circle(69,20,14,"gold",3); p.circle(69,20,5,"mana")
    elif name == "shield":
        p.polygon([(20,22),(50,12),(80,22),(76,60),(50,88),(24,60)],"border")
        p.polygon([(28,28),(50,21),(72,28),(67,57),(50,77),(33,57)])
        p.line([(50,27),(50,68)],4,"gold")
    elif name == "helm":
        p.polygon([(26,81),(24,42),(34,21),(50,13),(66,21),(76,42),(74,81),(56,88),(56,57),(44,57),(44,88)])
        p.line([(32,45),(44,49)],5,"panel"); p.line([(56,49),(68,45)],5,"panel")
        p.line([(50,16),(50,39)],3,"gold")
    elif name == "armor":
        p.polygon([(30,19),(42,26),(58,26),(70,19),(85,40),(75,54),(68,45),(71,84),(29,84),(32,45),(25,54),(15,40)])
        p.line([(50,31),(50,76)],3,"gold")
    elif name == "ring":
        p.circle(50,60,24,"gold",7)
        p.polygon([(50,10),(66,28),(50,43),(34,28)])
        p.line([(40,29),(60,29)],2,"border")
    elif name in ("flask", "poison"):
        p.polygon([(40,13),(60,13),(60,36),(77,60),(74,80),(64,88),(36,88),(26,80),(23,60),(40,36)],"gold" if name=="flask" else "stamina")
        p.line([(36,17),(64,17)],5,"border")
        p.polygon([(33,62),(65,55),(69,76),(61,81),(39,81),(31,75)],"panel")
        if name == "poison":
            p.circle(44,66,3); p.circle(56,66,3)
    elif name == "shard":
        p.polygon([(46,10),(72,29),(65,72),(40,91),(23,63),(31,34)],"gold")
        p.line([(46,14),(46,80),(64,33),(46,14),(31,36),(46,80)],2,"panel")
    elif name == "heart":
        p.circle(35,35,18,"hp"); p.circle(65,35,18,"hp")
        p.polygon([(17,37),(83,37),(77,56),(50,84),(23,56)],"hp")
        p.line([(27,47),(40,47),(45,36),(53,61),(60,47),(73,47)],3)
    elif name == "stamina":
        p.polygon([(58,11),(23,57),(47,57),(40,89),(78,41),(54,41)],"stamina")
    elif name == "bleed":
        p.polygon([(50,11),(74,51),(76,67),(65,83),(50,89),(35,83),(24,67),(26,51)],"hp")
        p.line([(35,61),(37,71),(44,76)],3)
    elif name == "frost":
        for a,b in (((50,12),(50,88)),((17,31),(83,69)),((17,69),(83,31))):
            p.line([a,b],4,"mana")
        for x,y in ((50,24),(28,38),(72,38),(28,62),(72,62),(50,76)):
            p.circle(x,y,5,"ink")
    elif name == "curse":
        p.circle(50,43,27,"muted"); p.polygon([(32,50),(68,50),(65,78),(35,78)],"muted")
        p.circle(39,43,7,"panel"); p.circle(61,43,7,"panel")
        p.line([(44,73),(44,86)],3,"panel"); p.line([(56,73),(56,86)],3,"panel")
    elif name == "healing":
        p.circle(50,50,34,"gold",2)
        p.polygon([(43,22),(57,22),(57,43),(78,43),(78,57),(57,57),(57,78),(43,78),(43,57),(22,57),(22,43),(43,43)])
    elif name == "map":
        p.line([(13,24),(37,14),(63,26),(87,16),(87,76),(63,86),(37,74),(13,84)],4,closed=True)
        p.line([(37,14),(37,74)],2,"gold"); p.line([(63,26),(63,86)],2,"gold")
        p.line([(23,52),(47,39),(75,58)],3,"border")
    elif name == "player":
        p.polygon([(50,14),(81,83),(50,68),(19,83)],"gold")
    elif name == "settings":
        p.circle(50,50,25,"gold",8); p.circle(50,50,8)
        for x,y in ((50,15),(50,85),(15,50),(85,50),(25,25),(75,75),(25,75),(75,25)):
            p.line([(50+(x-50)*.65,50+(y-50)*.65),(x,y)],9,"gold")
    elif name == "volume":
        p.polygon([(16,39),(32,39),(50,22),(50,78),(32,61),(16,61)])
        p.line([(62,31),(73,40),(75,50),(73,60),(62,69)],4,"gold")
        p.line([(77,19),(89,38),(91,50),(89,62),(77,81)],3,"border")
    elif name == "controls":
        p.line([(18,28),(82,28),(88,72),(12,72)],4,closed=True)
        for y in (40,52):
            for x in (26,42,58,74): p.line([(x,y),(x+3,y)],4,"gold")
        p.line([(30,63),(70,63)],4,"gold")
    elif name == "save":
        p.line([(21,14),(69,14),(81,26),(81,85),(21,85)],5,closed=True)
        p.line([(34,16),(34,40),(65,40),(65,16)],4,"gold")
        p.line([(34,83),(34,58),(68,58),(68,83)],4)
    elif name == "exit":
        p.line([(52,16),(22,16),(22,84),(52,84)],4)
        p.line([(45,50),(84,50),(69,34)],4,"gold"); p.line([(84,50),(69,66)],4,"gold")
    elif name in ("back", "chevron", "confirm"):
        points={"back":[(72,24),(28,50),(72,76)],"chevron":[(38,25),(64,50),(38,75)],"confirm":[(21,50),(42,72),(80,26)]}[name]
        p.line(points,6,"gold")
    elif name == "levels":
        p.line([(20,79),(20,58),(40,58),(40,41),(60,41),(60,23),(81,23)],5)
        p.line([(64,13),(82,13),(82,31)],4,"gold")
    elif name == "credits":
        p.polygon([(28,76),(36,43),(73,13),(86,23),(63,62)],"gold")
        p.line([(23,86),(72,35)],3,"ink"); p.line([(18,90),(80,90)],2,"border")
    return np.rint(p.pixels.reshape(112,2,112,2,4).mean(axis=(1,3))).astype(np.uint8)


def build_rgba(palette=PALETTE):
    canvas = np.zeros((SIZE, SIZE, 4), dtype=np.uint8)
    for index, name in enumerate(NAMES):
        tile = np.pad(draw_icon(name, palette), ((GUTTER,GUTTER),(GUTTER,GUTTER),(0,0)), mode="edge")
        x,y = index % 8 * CELL, index // 8 * CELL
        canvas[y:y+CELL,x:x+CELL] = tile
    return canvas


def palette_digest(palette=PALETTE):
    return hashlib.sha256(json.dumps(dict(palette),sort_keys=True).encode()).hexdigest()


def write_atlas(directory: Path, palette=PALETTE):
    directory.mkdir(parents=True, exist_ok=True)
    pixels = build_rgba(palette)
    def chunk(name, data):
        return struct.pack('!I',len(data))+name+data+struct.pack('!I',zlib.crc32(name+data)&0xffffffff)
    raw = b''.join(b'\0'+row.tobytes() for row in pixels)
    png = b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',SIZE,SIZE,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(raw,9))+chunk(b'IEND',b'')
    (directory/'atlas.png').write_bytes(png)
    report = dict(revision=REVISION,size=SIZE,cell=CELL,gutter=GUTTER,names=list(NAMES),
        palette_sha256=palette_digest(palette),png_sha256=hashlib.sha256(png).hexdigest())
    (directory/'atlas.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    return report


class SpriteAtlas:
    def __init__(self, directory: Path | None = None, palette=PALETTE):
        self.texture = Texture('vigilia-ui-atlas')
        self.source = 'procedural'
        try:
            report = json.loads((directory/'atlas.json').read_text(encoding='utf8'))
            path = directory/'atlas.png'
            valid = (report['revision']==REVISION and report['names']==list(NAMES)
                and report['palette_sha256']==palette_digest(palette)
                and report['png_sha256']==hashlib.sha256(path.read_bytes()).hexdigest())
            if valid and self.texture.read(Filename.from_os_specific(str(path))) and self.texture.get_x_size()==SIZE and self.texture.get_y_size()==SIZE:
                self.source = 'atlas'
        except (OSError, ValueError, TypeError, KeyError):
            pass
        if self.source != 'atlas':
            self.texture.setup_2d_texture(SIZE,SIZE,Texture.T_unsigned_byte,Texture.F_rgba8)
            self.texture.set_ram_image_as(np.flipud(build_rgba(palette)).tobytes(),'RGBA')
        self.texture.set_minfilter(Texture.FT_linear_mipmap_linear)
        self.texture.set_magfilter(Texture.FT_linear)
        self.texture.set_wrap_u(Texture.WM_clamp)
        self.texture.set_wrap_v(Texture.WM_clamp)
        self.texture.generate_ram_mipmap_images()

    @staticmethod
    def uv(name):
        index = NAMES.index(name if name in NAMES else 'shard')
        x,y = index%8*CELL+GUTTER,index//8*CELL+GUTTER
        return x/SIZE,(x+112)/SIZE,1-(y+112)/SIZE,1-y/SIZE

    def attach(self, parent, name, rect, *, frame=False):
        x,y,width,height = rect
        left,right,bottom,top = self.uv(name)
        if frame:
            corner=min(12,width/3,height/3)
            xs,ys=(x,x+corner,x+width-corner,x+width),(y,y+corner,y+height-corner,y+height)
            us,vs=(left,left+(right-left)*.22,right-(right-left)*.22,right),(top,top-(top-bottom)*.22,bottom+(top-bottom)*.22,bottom)
        else:
            xs,ys,us,vs=(x,x+width),(y,y+height),(left,right),(top,bottom)
        data=GeomVertexData('ui-sprite',GeomVertexFormat.get_v3t2(),Geom.UH_static)
        vertex,uv=GeomVertexWriter(data,'vertex'),GeomVertexWriter(data,'texcoord')
        triangles=GeomTriangles(Geom.UH_static)
        count=0
        for row in range(len(ys)-1):
            for col in range(len(xs)-1):
                # Frame centers contain no ink: avoid a transparent full-panel draw.
                if frame and row == col == 1:
                    continue
                for cx,cy in ((col,row),(col+1,row),(col+1,row+1),(col,row+1)):
                    vertex.add_data3(xs[cx],-.005,-ys[cy]); uv.add_data2(us[cx],vs[cy])
                triangles.add_vertices(count,count+2,count+1); triangles.add_vertices(count,count+3,count+2)
                count+=4
        geom=Geom(data); geom.add_primitive(triangles)
        node=GeomNode(name); node.add_geom(geom)
        path=parent.attach_new_node(node)
        path.set_texture(self.texture)
        path.set_transparency(TransparencyAttrib.M_alpha)
        path.set_depth_test(False); path.set_depth_write(False)
        return path
