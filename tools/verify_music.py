"""Native presentation QA with synthetic area/music events, not a playthrough."""

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main():
    from panda3d.core import PNMImage, Filename
    from vigilia.core.config import load_config
    from vigilia.core.events import MusicChangeRequestedEvent
    from vigilia.core.mathx import Vec3
    from vigilia.core.types import AppState
    from vigilia.engine.app import ArenaApp
    from vigilia.game import Game

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/music/native")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = ArenaApp(load_config(ROOT / "data/config.toml"))
    app.ignore("vigilia-button-down")
    app.ignore("vigilia-button-up")
    game = Game(app, load_config(ROOT / "data/config.toml"), ROOT / "assets",
        save_path=args.output / "save.sqlite3", settings_path=args.output / "settings.toml", enemy_count=0)
    app.start(game)
    # Presentation fixture: use real cathedral geometry without live combat.
    # This is deliberately separate from the production-rules balance run.
    cathedral = game._regions["catedral_submersa"]
    game._regions["catedral_submersa"] = replace(cathedral, enemies=())
    assert game._audio.enabled and game._music_director is not None
    # Catch any attempt to synthesize during area/combat presentation.
    from vigilia.engine import music_synthesis
    original = music_synthesis.synthesize
    def forbidden(*args, **kwargs):
        raise AssertionError("Music synthesis inside the running game")
    music_synthesis.synthesize = forbidden
    events, stage = [], 0
    started = time.monotonic()
    due = started + 2

    def record(label):
        audio = game._audio
        events.append(dict(label=label,seconds=round(time.monotonic() - started, 3),
            track=audio.track_id,levels=audio._levels.copy(),duck=audio._duck_gain,
            busy=[channel.get_busy() for channel in audio._music]))
        (args.output / "progress.json").write_text(json.dumps(events, indent=2), encoding="utf8")
        print(json.dumps(events[-1]), flush=True)

    def snapshot(name):
        image = PNMImage()
        assert app.win.get_screenshot(image)
        assert image.write(Filename.from_os_specific(str((args.output / (name + ".png")).resolve())))

    def request(track, fade=1.5):
        game._bus.publish(MusicChangeRequestedEvent(track, fade))

    def tick(task):
        nonlocal due, stage
        now = time.monotonic()
        if now < due:
            return task.cont
        if stage == 0:
            record("patio")
            snapshot("patio")
            game.change_area("catedral_submersa", Vec3(60, -6, 1.02))
            delay = .75
        elif stage == 1:
            record("area_midpoint")
            assert all(game._audio._music[i].get_busy() for i in range(2))
            assert all(.35 < level < .65 for level in game._audio._levels)
            delay = 1
        elif stage == 2:
            record("cathedral")
            snapshot("cathedral")
            assert game._audio.track_id == "cathedral_ambient"
            request("boss_phase1")
            delay = .25
        elif stage == 3:
            record("fog_out")
            assert game._audio.track_id == ""
            delay = .5
        elif stage == 4:
            record("boss_fade_in")
            assert game._audio.track_id == "boss_phase1"
            delay = 1
        elif stage == 5:
            request("boss_phase2", .5)
            delay = 1
        elif stage == 6:
            record("phase_midpoint")
            assert all(.35 < level < .65 for level in game._audio._levels)
            delay = 1.1
        elif stage == 7:
            request("", 3)
            delay = 1.5
        elif stage == 8:
            record("death_midpoint")
            assert .35 < max(game._audio._levels) < .65
            delay = 1.6
        elif stage == 9:
            record("death_silence")
            assert not any(channel.get_busy() for channel in game._audio._music)
            request("cathedral_ambient", 0)
            game.flow.push(AppState.PAUSED)
            game.flow.push(AppState.OPTIONS)
            delay = .8
        elif stage == 10:
            record("options")
            assert abs(game._audio._duck_gain - 10 ** (-6 / 20)) < .01
            game.flow.back()
            delay = .8
        elif stage == 11:
            record("options_closed")
            assert game._audio._duck_gain > .99
            request("ending_transform")
            delay = .1
        else:
            record("ending_one_shot")
            assert game._audio._music_loops["ending_transform"] is False
            report = dict(passed=True,real_mixer=True,scope=__doc__,
                synthesis_during_frames=False,events=events)
            (args.output / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf8")
            game.request_quit()
            return task.done
        stage += 1
        due = time.monotonic() + delay
        return task.cont

    app.taskMgr.add(tick, "verify-music-events", sort=60)
    try:
        app.run()
    finally:
        music_synthesis.synthesize = original
        app.destroy()


if __name__ == "__main__":
    main()
