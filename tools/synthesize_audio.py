"""Gera placeholders originais determinísticos; nunca executado pelo jogo."""

import argparse
from pathlib import Path
import wave
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
HZ = 44100


def write(path, signal):
    path.parent.mkdir(parents=True, exist_ok=True)
    signal = np.clip(signal, -1, 1)
    pcm = (signal * 32767).astype("<i2")
    stereo = np.column_stack((pcm, pcm))
    with wave.open(str(path), "wb") as wav:
        wav.setparams((2, 2, HZ, len(signal), "NONE", "not compressed"))
        wav.writeframes(stereo.tobytes())


def generate(output):
    rng = np.random.default_rng(46)
    # duration, frequency, decay, noise fraction, frequency sweep
    clips = {
        "swing_light": (.22, 180, 12, .8, -120), "swing_heavy": (.4, 105, 7, .8, -70),
        "hit_flesh": (.2, 70, 26, .7, -30), "hit_block": (.35, 820, 14, .35, -200),
        "parry": (.45, 1100, 12, .15, 200), "parry_spark": (.3, 2600, 18, .2, -300),
        "ui_ping": (.5, 1320, 9, 0, 0), "riposte": (.5, 85, 13, .6, -50),
        "backstab": (.4, 100, 17, .6, -65), "roll": (.35, 135, 12, .85, -100),
        "death_player": (1.3, 130, 3, .15, -65), "death_enemy": (.65, 110, 7, .25, -80),
        "level_up": (1.8, 440, 2, 0, 440), "soul_collect": (.7, 660, 6, .05, 600),
        "bonfire_rest": (1.5, 220, 3, .1, 110), "footstep_light": (.12, 95, 45, .85, -30),
        "footstep_heavy": (.19, 60, 28, .7, -20), "boss_roar": (1.1, 55, 3, .35, -25),
        "fog_wall_enter": (.8, 160, 4, .8, 60), "boss_death": (1.8, 65, 2.5, .5, -40),
        "drink": (.5, 350, 8, .4, -150),
    }
    for name, (duration, freq, decay, noise, sweep) in clips.items():
        t = np.arange(round(duration * HZ)) / HZ
        phase = 2 * np.pi * (freq * t + sweep * t * t / (2 * duration))
        tone = np.sin(phase) + .25 * np.sin(phase * 2.37)
        # Ruído filtrado evita hiss agressivo e clipping de transientes.
        raw = rng.normal(0, 1, len(t))
        filtered = np.convolve(raw, np.ones(12) / 12, mode="same")
        signal = ((1 - noise) * tone + noise * filtered) * np.exp(-decay * t)
        signal *= np.minimum(1, t / .006) * np.minimum(1, (duration - t) / .025)
        signal *= .65 / max(.01, np.max(np.abs(signal)))
        write(output / "sfx" / (name + ".wav"), signal)
    for name, root, pulse in (("menu_theme", 110, .5), ("patio_ambient", 82.5, .5),
                              ("forge_ambient", 55, 1), ("boss_phase1", 73.333333, 2),
                              ("boss_phase2", 110, 4), ("cathedral_ambient", 92.5, .5),
                              ("marsh_ambient", 61.666667, .25), ("tide_boss_phase1", 98, 1.5),
                              ("tide_boss_phase2", 146.666667, 3), ("ruins_ambient", 49, .25),
                              ("furnace_ambient", 41.25, .5), ("cinder_boss_phase1", 65.416667, 2),
                              ("cinder_boss_phase2", 82.416667, 3), ("cinder_boss_phase3", 110, 4)):
        duration = 12
        t = np.arange(duration * HZ) / HZ
        # Frequências inteiras de ciclos/12s, com modulações periódicas: loop sem clique.
        signal = np.zeros(len(t))
        for ratio, gain in ((1, .1), (1.5, .06), (2, .035), (2.4, .025)):
            freq = round(root * ratio * duration) / duration
            signal += np.sin(2 * np.pi * freq * t) * gain * (.75 + .25 * np.cos(2 * np.pi * t / 12))
        beat = np.exp(-((t * pulse) % 1) * 18)
        signal += np.sin(2 * np.pi * 44 * t) * beat * (.1 if "boss" in name else .025)
        write(output / "music" / (name + ".wav"), signal)
    print(f"Gerados {len(clips)} SFX e 14 loops em {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "assets/audio")
    generate(parser.parse_args().output)
