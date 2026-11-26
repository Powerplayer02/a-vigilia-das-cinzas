"""Eight-voice audio stress: offline PCM measurement and real-mixer presentation QA."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import time
import wave

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from vigilia.core.events import EventBus, SfxRequestedEvent
from vigilia.engine.audio import AudioBackend, AudioEventRouter
from vigilia.engine.sfx_synthesis import SPECS, ensure_sfx


class PCMSound:
    def __init__(self, path):
        with wave.open(path) as stream:
            self.frames = stream.getnframes()
            self.samples = np.frombuffer(stream.readframes(min(self.frames, 44100 * 4)), dtype="<i2").reshape(-1, 2).astype(float) / 32768


class PCMChannel:
    def __init__(self):
        self.sound = None
        self.cursor = self.loops = 0
        self.volume = (1., 1.)

    def play(self, sound, loops=0):
        self.sound, self.cursor, self.loops = sound, 0, loops

    def stop(self):
        self.sound = None

    def get_busy(self):
        return self.sound is not None

    def set_volume(self, *values):
        values = values * 2 if len(values) == 1 else values
        self.volume = tuple(math.floor(value * 128) / 128 for value in values)

    def render(self, frames):
        output = np.zeros((frames, 2))
        if self.sound is None:
            return output
        offset = 0
        while offset < frames and self.sound is not None:
            count = min(frames - offset, len(self.sound.samples) - self.cursor)
            output[offset:offset + count] += self.sound.samples[self.cursor:self.cursor + count] * self.volume
            self.cursor += count
            offset += count
            if self.cursor >= len(self.sound.samples):
                if self.loops == -1:
                    self.cursor = 0
                else:
                    self.sound = None
        return output


class PCMMixer:
    def get_init(self):
        return True

    def set_num_channels(self, count):
        self.channels = [PCMChannel() for _ in range(count)]

    def set_reserved(self, count):
        self.reserved = count

    def Channel(self, index):
        return self.channels[index]

    def Sound(self, path):
        return PCMSound(path)


def saturate(bus):
    for _ in range(6):
        bus.publish(SfxRequestedEvent("footstep_stone"))
    for key in ("ui_confirm", "ui_error", "parry", "boss_death", "boss_phase2", "riposte", "hit_armor"):
        bus.publish(SfxRequestedEvent(key))


def offline(output):
    ensure_sfx(ROOT / "assets/sfx")
    mixer = PCMMixer()
    audio = AudioBackend(ROOT / "assets", mixer=mixer, channels=8, enhanced_sfx=True,
        music_directory=ROOT / "assets/music", sfx_directory=ROOT / "assets/sfx",
        buses={"combat": 1, "ui": .9, "ambient": .6, "music": .7})
    audio.set_volumes(1, 1, 1)
    audio.play_music("cinder_boss_phase3", fade_sec=0)
    bus = EventBus()
    AudioEventRouter(bus, audio, ROOT / "data/audio/sfx.toml")
    saturate(bus)
    assert all(v.channel.get_busy() for v in audio.voices)
    blocks = []
    for _ in range(180):
        audio.update(1 / 60)
        blocks.append(sum((channel.render(735) for channel in mixer.channels), np.zeros((735, 2))))
    mixed = np.concatenate(blocks)
    peak = float(np.abs(mixed).max())
    assert peak <= 10 ** (-1 / 20), "Additive PCM mixture clips; no limiter applied to exported samples"
    path = output / "boss-eight-voices.wav"
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(2)
        stream.setsampwidth(2)
        stream.setframerate(44100)
        stream.writeframes(np.rint(mixed * 32767).astype("<i2").tobytes())
    audio.close()
    reports = [json.loads(path.read_text()) for path in (ROOT / "assets/sfx").glob("*.json")]
    return dict(peak_dbfs=20 * math.log10(peak), simultaneous_sfx=8, reserved_ui=2,
        music_channels_additional=2, sliders="all 100%", output=str(path),
        mixture_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        generated_clips=len(reports), maximum_asset_peak_dbfs=max(row["peak_dbfs"] for row in reports),
        assets_bytes=sum(path.stat().st_size for path in (ROOT / "assets/sfx").glob("*.wav")),
        scope="Offline additive PCM using production gain/preemption policy, not a speaker recording or listening assessment")


def native(output):
    from panda3d.core import PNMImage, Filename
    from vigilia.core.config import load_config
    from vigilia.core.events import BossArenaEnteredEvent
    from vigilia.core.mathx import Vec3
    from vigilia.engine.app import ArenaApp
    from vigilia.game import Game
    app = ArenaApp(load_config(ROOT / "data/config.toml"))
    app.ignore("vigilia-button-down")
    app.ignore("vigilia-button-up")
    game = Game(app, load_config(ROOT / "data/config.toml"), ROOT / "assets", enemy_count=0,
        save_path=output / "native.sqlite3", settings_path=output / "settings.toml", sfx_channels=8)
    app.start(game)
    app.graphicsEngine.render_frame()
    app.graphicsEngine.render_frame()
    monitor = game.enable_diagnostics(output / "spikes", report_path=output / "diagnostics.json")
    assert game._audio.enabled and len(game._audio.voices) == 8
    started = time.monotonic()
    stage = 0
    images = []
    rows = []

    def tick(task):
        nonlocal stage
        age = time.monotonic() - started
        if stage == 0 and age >= 1:
            game._bus.publish(BossArenaEnteredEvent(game.boss.profile.id, game.boss.profile.arena, Vec3(0, 15.2, 1.02)))
            stage = 1
        elif stage == 1 and age >= 2:
            for voice in game._audio.voices:
                voice.channel.stop()
            saturate(game._bus)
            rows.extend(dict(index=i + 2, priority=v.priority, bus=v.bus, ui_reserved=v.ui_reserved,
                playing=v.channel.get_busy(), sound_matches_catalogue=v.channel.get_sound() in game._audio._sounds.values())
                for i, v in enumerate(game._audio.voices))
            assert all(row["playing"] and row["sound_matches_catalogue"] for row in rows)
            assert sum(row["ui_reserved"] and row["bus"] == "ui" for row in rows) == 2
            image = PNMImage()
            assert app.win.get_screenshot(image)
            images.append(image)
            stage = 2
        elif stage == 2 and age >= 4:
            game.request_quit()
            return task.done
        return task.cont

    app.taskMgr.add(tick, "eight-sfx-native", sort=60)
    try:
        app.run()
    finally:
        app.destroy()
    for index, image in enumerate(images):
        assert image.write(Filename.from_os_specific(str((output / f"native-{index}.png").resolve())))
    return dict(real_mixer=True, actual_channels=rows, quarantined=monitor.quarantined,
        diagnostics=monitor.report(), scope="Canonical event injection inside a live boss arena; audio stress fixture, not a balance playthrough")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/sfx/verification")
    parser.add_argument("--native", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = native(args.output) if args.native else offline(args.output)
    (args.output / ("native.json" if args.native else "offline.json")).write_text(json.dumps(report, indent=2), encoding="utf8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
