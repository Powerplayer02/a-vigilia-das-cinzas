"""Atlas content, fallback parity, filtering and UI state without a window."""
from dataclasses import replace
import hashlib
import json

import numpy as np
from panda3d.core import NodePath, Texture
import pytest

from vigilia.core.palette import PALETTE, DEFAULTS, load_palette
from vigilia.core.views import StatusView
from vigilia.engine.sprite_atlas import (NAMES, CELL, GUTTER, SIZE, SpriteAtlas,
    build_rgba, write_atlas)
from vigilia.engine.ui import fallback_text
from vigilia.ui.hud import HUD
from ui_fakes import BackendFake, QueryFake


@pytest.fixture(scope="module")
def atlas_pixels():
    return build_rgba()


def test_palette_has_validated_roles_and_missing_file_fallback(tmp_path):
    assert dict(load_palette(tmp_path/'missing.toml')) == DEFAULTS == dict(PALETTE)
    for value in ('[1, 2, 0, 1]', '[true, 0, 0, 1]', '[0, 0]', '[nan, 0, 0, 1]'):
        p=tmp_path/'invalid.toml'
        p.write_text('version=1\n[colors]\nink='+value)
        with pytest.raises(ValueError): load_palette(p)
    p.write_text('version=1\n[colors]\ngold=[1,0.5,0,1]')
    assert load_palette(p)['gold'] == (1,.5,0,1)


def test_engine_font_fallback_keeps_readable_equivalents_for_missing_glyphs():
    assert fallback_text('Ação ×3 · Vésper — Fé → 12…') == 'Acao x3 / Vesper - Fe -> 12...'


def test_each_icon_is_distinct_nonempty_and_has_extruded_gutter(atlas_pixels):
    hashes=[]
    for index,name in enumerate(NAMES):
        x,y=index%8*CELL,index//8*CELL
        tile=atlas_pixels[y:y+CELL,x:x+CELL]
        assert np.count_nonzero(tile[:,:,3]) > 50, name
        assert np.array_equal(tile[:GUTTER], np.repeat(tile[GUTTER:GUTTER+1],GUTTER,axis=0))
        assert np.array_equal(tile[:,:GUTTER], np.repeat(tile[:,GUTTER:GUTTER+1],GUTTER,axis=1))
        if name not in ('panel','button','soul'):
            hashes.append(hashlib.sha256(tile.tobytes()).hexdigest())
        left,right,bottom,top=SpriteAtlas.uv(name)
        assert 0<=left<right<=1 and 0<=bottom<top<=1
        assert right-left == top-bottom == 112/SIZE
    assert len(set(hashes))==len(hashes)


def test_disk_and_empty_assets_have_identical_mipmapped_texture(tmp_path):
    report=write_atlas(tmp_path)
    disk, fallback=SpriteAtlas(tmp_path),SpriteAtlas(tmp_path/'empty')
    assert disk.source=='atlas' and fallback.source=='procedural'
    assert bytes(disk.texture.get_ram_image_as('RGBA')) == bytes(fallback.texture.get_ram_image_as('RGBA'))
    for atlas in (disk,fallback):
        assert atlas.texture.get_minfilter()==Texture.FT_linear_mipmap_linear
        assert atlas.texture.get_magfilter()==Texture.FT_linear
        assert atlas.texture.get_num_ram_mipmap_images() == 11
    assert report['png_sha256']==hashlib.sha256((tmp_path/'atlas.png').read_bytes()).hexdigest()
    (tmp_path/'atlas.png').write_bytes(b'corrupt')
    assert SpriteAtlas(tmp_path).source=='procedural'
    write_atlas(tmp_path)
    metadata=json.loads((tmp_path/'atlas.json').read_text())
    metadata['palette_sha256']='stale'
    (tmp_path/'atlas.json').write_text(json.dumps(metadata))
    assert SpriteAtlas(tmp_path).source=='procedural'


def test_nine_slice_is_one_mesh_with_preserved_corner_size_and_unknown_fallback():
    atlas=SpriteAtlas()
    frame=atlas.attach(NodePath('root'),'panel',(0,0,400,180),frame=True)
    assert frame.node().get_num_geoms()==1
    geom=frame.node().get_geom(0)
    assert geom.get_vertex_data().get_num_rows()==32
    assert geom.get_primitive(0).get_num_primitives()==16
    assert atlas.uv('missing')==atlas.uv('shard')


def test_hud_sprites_follow_equipment_spell_and_status_without_rebuilding():
    backend, query=BackendFake(),QueryFake()
    hud=HUD(backend,query)
    query.vitals=replace(query.vitals,weapon_icon='axe',spell_kind='healing')
    query.statuses=[StatusView('poison','Veneno','V',1)]
    hud.tick()
    assert backend.nodes['hud.weapon_icon']['sprite']=='axe'
    assert backend.nodes['hud.spell.glyph']['sprite']=='healing'
    assert [backend.nodes[f'hud.condition.{i}']['visible'] for i in range(4)] == [False,True,False,False]
    snapshot=tuple(backend.nodes)
    backend.updates.clear()
    hud.tick()
    assert not backend.updates and tuple(backend.nodes)==snapshot
