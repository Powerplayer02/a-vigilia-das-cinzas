"""Native UI gallery and layout checks with temporary presentation fixtures.

This is UI QA, not a balance playthrough. Only a temporary save is modified.
PNG encoding is outside performance measurements.
"""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from panda3d.core import Filename
from vigilia.core.config import Config
from vigilia.core.types import AppState
from vigilia.core.views import BossView
from vigilia.engine.app import ArenaApp
from vigilia.game import Game
from vigilia.combat.status import StatusEffect
from vigilia.ui.dialog import Dialog


def verify(output, width, height, empty_assets=False):
    output.mkdir(parents=True,exist_ok=True)
    config=Config(width=width,height=height,vsync=False)
    app=ArenaApp(config,window_type='offscreen')
    rows=[]
    try:
        with tempfile.TemporaryDirectory(prefix='vigilia-sprites-') as temp:
            directory=Path(temp)
            assets=directory/'empty-assets' if empty_assets else ROOT/'assets'
            assets.mkdir(exist_ok=True)
            if empty_assets:
                shutil.copytree(ROOT/'data',directory/'data',ignore=shutil.ignore_patterns('settings.toml'))
            game=Game(app,config,assets,save_path=directory/'ui.sqlite3',
                settings_path=directory/'settings.toml',enemy_count=0,front_end=True)
            app.start(game)
            app.taskMgr.remove('vigilia-update')
            b=game.ui_backend
            for _ in range(3): game.frame(1/60,(0,0),(0,0))

            def capture(name):
                b.root.set_alpha_scale(1)
                # Settle presentation fades without ticking gameplay or menus.
                for _ in range(12):b.tick(1/60)
                assert not getattr(b,'_closing_panels',[])
                for _ in range(3): app.graphicsEngine.render_frame()
                path=output/(name+'.png')
                assert app.win.save_screenshot(Filename.from_os_specific(str(path.resolve())))
                overflow=[]
                for key,label in b.label_paths.items():
                    if b.nodes[key].is_hidden(): continue
                    bounds=label.get_tight_bounds(b.nodes[key])
                    if bounds is None: continue
                    low,high=bounds
                    _,_,w,h=b.rects[key]
                    if low.x < -2 or high.x > w+3 or -low.z > h+4:
                        overflow.append(dict(key=key,content=b.labels[key].get_text(),
                            rendered=[round(low.x,2),round(high.x,2),round(-low.z,2)],box=[w,h]))
                rows.append(dict(screen=name,image=path.name,overflows=overflow))

            capture('main-menu')
            game.front.show(AppState.SLOT_SELECT); capture('slots')
            game.front.show(AppState.CHARACTER_CREATION); capture('character-creation')
            for index in range(1,len(game.front.screen.classes)):
                game.front.screen.select_class(index)
                capture('character-'+game.front.screen.classes[index].id)
            game.front.show(AppState.OPTIONS)
            for index,category in enumerate(('graphics','audio','controls','language','accessibility')):
                game.front.screen.select_category(index); capture('options-'+category)
            native_slider = b.nodes['front.slider.hud_scale']
            native_slider['value'] = 1.5
            game.front.screen.set_slider(0,float(native_slider['value']))
            assert game.settings.options.hud_scale == 1.5
            assert native_slider.guiItem.get_value() == 1.5
            assert '150%' in b.labels['front.option.hud_scale'].get_text()
            capture('options-hud-150')
            native_slider['value'] = 1.0
            game.front.screen.set_slider(0,float(native_slider['value']))
            game.front.show(AppState.CREDITS); capture('credits')
            modal=Dialog(b,'common.confirm','Confirmação de exemplo. Seu save não será alterado.',lambda:None,lambda:None)
            capture('dialog'); modal.root.destroy()
            game.front.close()
            for page in ('pause','status','inventory','equipment','level','map','ending'):
                game.menus.open(page); capture(page)
            game.menus.content.review('transform'); capture('ending-confirmation')
            game.menus.close()
            game._fighter.status.active={StatusEffect.POISON:600}
            game._fighter.status.buildup={StatusEffect.BLEED:42}
            game.hud.root.show(); game.hud.tick()
            capture('hud')
            game.hud.query=SimpleNamespace(player_vitals=lambda: replace(game.queries.player_vitals(),
                spell_name='Brasa pulsante',spell_kind='arcane',spell_hint='E',spell_stamina=24,spell_ready=True),
                active_statuses=game.queries.active_statuses,
                active_boss=lambda:BossView('Custódio da Última Brasa',734,4700,3))
            game.hud.tick(); capture('hud-boss')
            game.hud.accessibility(1.5,True); capture('hud-accessible')
            assert all(label.get_font().this==b.font.this for label in b.labels.values())
            result=dict(resolution=[width,height],screens=rows,atlas_source=b.atlas.source,
                mipmaps=b.atlas.texture.get_num_ram_mipmap_images(),shared_font=True,
                font_source='cmss12 (engine fallback)' if empty_assets else 'assets/fonts/ui.ttf',
                font_sha256=None if empty_assets else hashlib.sha256((assets/'fonts/ui.ttf').read_bytes()).hexdigest(),
                empty_assets=empty_assets,scope='Presentation fixtures; not human perception or gameplay difficulty')
            (output/'report.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf8')
            print(json.dumps(dict(resolution=result['resolution'],screens=len(rows),
                overflows=sum(len(r['overflows']) for r in rows),atlas_source=result['atlas_source']),indent=2))
    finally:
        app.destroy()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--width',type=int,default=1280)
    p.add_argument('--height',type=int,default=720)
    p.add_argument('--output',type=Path,default=ROOT/'artifacts/sprites/gallery-720')
    p.add_argument('--empty-assets',action='store_true')
    a=p.parse_args()
    verify(a.output,a.width,a.height,a.empty_assets)
