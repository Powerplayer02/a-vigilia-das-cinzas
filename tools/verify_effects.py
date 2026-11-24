"""Integração nativa dos eventos, mixagem, partículas e transições da 4.6."""

import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from panda3d.core import Filename
from vigilia.core.config import Config
from vigilia.core.events import (
    SfxRequestedEvent, SoulCollectedEvent, LevelUpEvent, BossArenaEnteredEvent,
    MusicChangeRequestedEvent, AreaEnteredEvent,
)
from vigilia.core.mathx import Vec3, Transform
from vigilia.core.types import AppState
from vigilia.combat.events import DamageDealt, ParrySucceeded, HPChangedEvent, EntityDied
from vigilia.engine.app import ArenaApp
from vigilia.game import Game


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--silent", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/4.6")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    config = Config(vsync=False)
    app = ArenaApp(config, window_type="offscreen")
    try:
        with tempfile.TemporaryDirectory(prefix="vigilia-effects-qa-") as directory:
            temporary = Path(directory)
            assets = ROOT / "assets"
            if args.silent:
                assets = temporary / "assets"
                shutil.copytree(ROOT / "assets", assets, ignore=shutil.ignore_patterns("audio"))
                shutil.copytree(ROOT / "data", temporary / "data")
            game = Game(app, config, assets, save_path=temporary / "slots.sqlite3", enemy_count=0, front_end=True)
            app.start(game)
            app.taskMgr.remove("vigilia-update")
            assert game._audio.enabled != args.silent
            observed = []
            original = game._audio.play_sfx
            def record(clip, **kwargs):
                result = original(clip, **kwargs)
                observed.append((clip, result))
                return result
            game._audio.play_sfx = record
            game._set_option(json.dumps({"key": "master_volume", "delta": -1}))
            assert game._audio.master_volume == game.settings.options.master_volume
            game.flow.transition(AppState.PLAYING)
            game._practice_wait = 10000

            def advance(count=1):
                for _ in range(count):
                    game.frame(1 / 60, (0, 0), (0, 0))

            def capture(name):
                for _ in range(2):
                    app.graphicsEngine.render_frame()
                assert app.win.save_screenshot(Filename.from_os_specific(str(args.output / name)))

            advance(4)
            game._particles.clear()
            point = game._transform.position + Vec3(0, 0, .7)
            game._bus.publish(DamageDealt(999, game._entity.id, 10, game._fighter.hp, False, ""))
            assert game._particles.pool.active_count == 12
            advance(3)
            capture("blood-silent.png" if args.silent else "blood.png")
            game._particles.clear()
            for voice in game._audio.voices:
                voice.channel.stop()
            game._bus.publish(ParrySucceeded(game._entity.id, 999))
            assert game._particles.pool.active_count == 8
            layers = sum(voice.channel.get_busy() for voice in game._audio.voices)
            assert layers == (0 if args.silent else 3)
            advance(8)
            capture("parry-silent.png" if args.silent else "parry.png")
            game._particles.clear()
            game._bus.publish(SoulCollectedEvent(point + Vec3(1, 0), 80))
            assert game._particles.pool.active_count == 20
            advance(20)
            game._bus.publish(LevelUpEvent(point))
            assert game._particles.pool.active_count == 50
            advance(10)
            capture("level-silent.png" if args.silent else "level.png")

            # Movimento real usa os mesmos emissores de passos e esquiva.
            game.keyboard("w", True)
            advance(40)
            game.keyboard("w", False)
            advance(2)
            game.keyboard("space", True)
            advance(2)
            game.keyboard("space", False)
            assert any(clip.startswith("footstep_") for clip, _ in observed)
            assert any(clip == "roll" for clip, _ in observed)
            for kind in game._audio_events.mapping:
                game._bus.publish(SfxRequestedEvent(kind, point))
            assert {clip for clip, _ in observed} >= {"swing_light", "swing_heavy", "hit_flesh", "hit_block",
                "parry", "riposte", "backstab", "roll", "death_player", "death_enemy", "level_up",
                "soul_collect", "bonfire_rest", "footstep_light", "footstep_heavy", "boss_roar", "fog_wall_enter"}

            game._bus.publish(AreaEnteredEvent("forge_arena"))
            assert game.music_track == "forge_ambient"
            game._audio.update(1.5)
            boss = game.boss
            game._bus.publish(BossArenaEnteredEvent(boss.profile.id, boss.profile.arena, Vec3(0, 25, 1.1)))
            assert game._polish.overlay.get_color()[3] == 1
            assert game.music_track == "boss_phase1"
            advance(20)
            assert game._polish.overlay.is_hidden()
            game._particles.clear()
            boss.fighter.hp = 1500
            game._bus.publish(HPChangedEvent(boss.entity.id, 3200, 1500, 3200, "player"))
            assert game.music_track == "boss_phase2" and game._audio._fade_duration == (.5 if not args.silent else 0)
            assert game._particles.pool.active_count == 60
            advance(35)
            assert game._particles.root.get_bounds().get_center().y > 10
            capture("boss-embers-silent.png" if args.silent else "boss-embers.png")
            boss.fighter.hp = 0
            game._bus.publish(EntityDied(boss.entity.id))
            advance(240)
            assert game.music_track == ""
            game._audio.update(1)
            assert not any(channel.get_busy() for channel in game._audio._music)

            # Tela preta cobre a espera de respawn; apresentação revela o checkpoint.
            game._fighter.hp = 0
            game._bus.publish(EntityDied(game._entity.id))
            advance(10)
            assert game._polish.overlay.get_color()[3] == 1
            advance(120)
            assert game._fighter.alive and game._polish.overlay.is_hidden()
            report = {"result": "ok", "silent": args.silent, "audio_enabled": game._audio.enabled,
                "parry_concurrent_layers": layers, "sound_clips_requested": sorted({clip for clip, _ in observed}),
                "particle_capacity": len(game._particles.pool.slots), "particle_draw_batches": len(game._particles.nodes),
                "fog_fade": True, "death_fade_respawn": True, "boss_music_stopped": True,
                "fixed_step_preserved": True}
            (args.output / ("effects-silent.json" if args.silent else "effects.json")).write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(report, indent=2))
            game.close()
            game.close()  # SDL real também precisa aceitar encerramento repetido.
    finally:
        app.destroy()


if __name__ == "__main__":
    main()
