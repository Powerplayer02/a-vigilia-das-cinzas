"""Seeded original sound effects. Offline synthesis only, no mixer or window."""

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import tempfile
import wave

import numpy as np

VERSION = 1
RATE = 44100


@dataclass(frozen=True)
class SfxSpec:
    family: str
    duration: float
    frequency: float
    noise: float
    attack: float
    decay: float
    sustain: float
    release: float
    sweep: float = 0
    peak_dbfs: float = -4


SPECS = {}
PRESETS = {}


def _add(kind, family, duration, frequency, *, variants=1, bus="combat", priority=40,
         noise=.5, gain=.8, attack=.004, decay=.045, sustain=.25, release=.06, sweep=-100):
    clips = []
    for index in range(variants):
        key = kind if variants == 1 else f"{kind}_{index + 1}"
        SPECS[key] = SfxSpec(family, duration, frequency * (1 + (index - (variants - 1) / 2) * .065),
            noise, attack, decay, sustain, release, sweep, -6 if bus == "ui" else -9 if bus == "ambient" else -4)
        clips.append(key)
    PRESETS[kind] = dict(variants=clips, bus=bus, priority=priority, gain=gain)


# Shared families tie the sound vocabulary to the score, with distinct weapon colors.
for weapon, frequency in (("longsword", 220), ("axe", 115), ("katana", 350), ("staff", 430), ("mace", 90)):
    _add(f"{weapon}_light", "whoosh", .24, frequency, variants=3, noise=.8)
    for move, duration, multiplier in (("heavy", .38, .6), ("running", .3, 1.1), ("dash_attack", .22, 1.3), ("slide_attack", .32, .75)):
        _add(f"{weapon}_{move}", "whoosh", duration, frequency * multiplier, noise=.75)

for kind, family, duration, frequency, noise, priority in (
    ("hit_flesh", "impact", .18, 75, .85, 40),
    ("hit_armor", "metal", .25, 620, .35, 40),
    ("hit_shield", "metal", .26, 410, .3, 40),
    ("hit_block", "metal", .22, 740, .25, 40),
    ("parry", "metal", .36, 1400, .08, 70),
    ("parry_fail", "whoosh", .16, 280, .8, 20),
    ("riposte", "impact", .38, 88, .6, 65),
    ("backstab", "impact", .34, 105, .7, 65),
    ("stagger_light", "impact", .18, 110, .6, 45),
    ("stagger_heavy", "metal", .32, 210, .4, 50),
    ("death_player", "fall", .4, 110, .6, 60),
    ("death_enemy", "fall", .35, 95, .8, 50),
    ("roll", "whoosh", .3, 150, .85, 20),
    ("dash", "whoosh", .2, 450, .65, 25),
    ("slide", "scrape", .38, 100, .9, 20),
    ("wall_cling", "scrape", .2, 230, .8, 20),
    ("wall_jump", "whoosh", .22, 550, .55, 25),
    ("slam", "impact", .4, 55, .65, 55),
    ("slam_descent", "whoosh", .3, 400, .8, 25),
    ("drink", "water", .35, 360, .4, 30),
):
    _add(kind, family, duration, frequency, noise=noise, priority=priority)

for surface, frequency, family in (("stone", 120, "impact"), ("mud", 65, "water"),
                                    ("wood", 190, "impact"), ("water", 430, "water")):
    _add("footstep_" + surface, family, .16, frequency, variants=3, priority=10, noise=.8, gain=.55)

for effect, frequency in (("bleed", 85), ("poison", 210), ("frost", 1700), ("curse", 130)):
    _add("status_" + effect, "metal" if effect == "frost" else "impact", .22, frequency, priority=35)
    _add("status_" + effect + "_tick", "metal" if effect == "frost" else "water", .12, frequency, priority=25, gain=.5)

for kind, frequency, duration in (("ui_open", 440, .14), ("ui_close", 330, .12),
    ("ui_hover", 880, .055), ("ui_click", 1100, .075), ("ui_back", 660, .09),
    ("ui_confirm", 1320, .16), ("ui_error", 196, .18), ("level_up", 523.25, .2),
    ("item_acquired", 784, .18), ("soul_collect", 987.77, .14), ("ui_change", 740, .07)):
    _add(kind, "ui", duration, frequency, noise=0, priority=60 if kind in ("ui_error", "ui_confirm") else 30,
         bus="ui", gain=.9, attack=.003, decay=.02, sustain=.5, release=min(.05, duration / 3), sweep=120)

for kind, family, frequency, duration in (("bonfire_light", "fire", 130, 1.4),
    ("bonfire_rest", "fire", 220, 1.4), ("bonfire_ambient", "fire", 80, 2),
    ("area_transition", "whoosh", 160, 1.1), ("shortcut_open", "scrape", 75, 1),
    ("door_open", "scrape", 90, 1), ("door_close", "impact", 60, 1),
    ("fog_wall_enter", "whoosh", 180, 1), ("fog_wall_exit", "whoosh", 260, 1),
    ("chest_open", "scrape", 240, 1), ("item_pickup", "metal", 1100, 1)):
    _add(kind, family, duration, frequency, bus="ambient", priority=15, noise=.65, release=.3, attack=.03, decay=.2)

for kind, frequency, duration in (("cast_arcane", 520, .35), ("magic_impact", 880, .32),
                                  ("magic_dissipate", 1300, .25), ("cast_heal", 660, .35), ("healing", 780, .3)):
    _add(kind, "magic", duration, frequency, noise=.15, sweep=700, priority=45)

for kind, frequency, priority, duration in (("boss_roar", 58, 85, 1.5),
    ("boss_phase", 73, 90, 1.6), ("boss_phase2", 82, 95, 1.5),
    ("boss_death", 49, 80, 2.2)):
    _add(kind, "roar", duration, frequency, priority=priority, noise=.4, release=.4, attack=.025, decay=.15)

# Backward-compatible event names and cues with no new generated duplicate.
PRESETS["swing_light"] = PRESETS["longsword_light"].copy()
PRESETS["swing_heavy"] = PRESETS["longsword_heavy"].copy()
PRESETS["footstep_light"] = PRESETS["footstep_stone"].copy()
PRESETS["footstep_heavy"] = PRESETS["footstep_stone"] | {"gain": .7}
PRESETS["ui_ping"] = PRESETS["ui_confirm"].copy()


def seed_for(clip_id):
    return int.from_bytes(hashlib.sha256(clip_id.encode("utf8")).digest()[:8], "little")


def synthesize(clip_id, seed=None, *, rate=RATE):
    spec = SPECS[clip_id]
    rng = np.random.Generator(np.random.PCG64(seed_for(clip_id) if seed is None else seed))
    t = np.arange(round(rate * spec.duration), dtype=float) / rate
    raw = rng.uniform(-1, 1, len(t))
    noise = np.convolve(raw, np.ones(7) / 7, mode="same")
    phase = 2 * np.pi * (spec.frequency * t + spec.sweep * t * t / (2 * spec.duration))
    tone = np.sin(phase)
    if spec.family == "metal":
        tone += .45 * np.sin(phase * 2.68) * np.exp(-t * 12) + .2 * np.sin(phase * 4.3) * np.exp(-t * 20)
    elif spec.family in ("fire", "scrape"):
        noise = np.tanh(np.cumsum(noise) / 5) * .5 + noise * .5
    elif spec.family == "roar":
        tone = np.tanh(2 * tone + .4 * np.sin(phase * .5)) * (.75 + .25 * np.sin(2 * np.pi * 7 * t))
    elif spec.family in ("water", "magic"):
        tone += .3 * np.sin(phase * 1.5 + .3 * np.sin(2 * np.pi * 23 * t))
    elif spec.family == "ui":
        tone += .2 * np.sin(phase * 1.5) + .1 * np.sin(phase * 2)
    amplitude = np.where(t < spec.attack, t / spec.attack,
        np.where(t < spec.attack + spec.decay,
                 1 - (1 - spec.sustain) * (t - spec.attack) / spec.decay, spec.sustain))
    amplitude *= np.clip((spec.duration - t) / spec.release, 0, 1)
    signal = ((1 - spec.noise) * tone + spec.noise * noise) * amplitude
    signal[0] = signal[-1] = 0
    signal *= 10 ** (spec.peak_dbfs / 20) / max(1e-12, np.max(np.abs(signal)))
    mono = np.rint(np.round(signal, 7) * 32767).astype("<i2")
    return np.column_stack((mono, mono))


def write_sfx(directory, clip_id, seed=None):
    directory = Path(directory)
    seed = seed_for(clip_id) if seed is None else seed
    pcm = synthesize(clip_id, seed)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (clip_id + ".wav")
    with tempfile.NamedTemporaryFile(dir=directory, suffix=".wav.tmp", delete=False) as stream:
        temporary = Path(stream.name)
    try:
        with wave.open(str(temporary), "wb") as stream:
            stream.setnchannels(2)
            stream.setsampwidth(2)
            stream.setframerate(RATE)
            stream.writeframes(pcm.tobytes())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    metadata = dict(version=VERSION, clip_id=clip_id, seed=seed, parameters=asdict(SPECS[clip_id]),
        rate=RATE, peak_dbfs=float(20 * np.log10(np.abs(pcm.astype(np.int32)).max() / 32768)),
        sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    path.with_suffix(".json").write_text(json.dumps(metadata, indent=2), encoding="utf8")
    return path, metadata


def ensure_sfx(directory):
    directory = Path(directory)
    for clip_id, spec in SPECS.items():
        path = directory / (clip_id + ".wav")
        try:
            metadata = json.loads(path.with_suffix(".json").read_text(encoding="utf8"))
            valid = (metadata["version"] == VERSION and metadata["seed"] == seed_for(clip_id)
                and metadata["parameters"] == asdict(spec)
                and metadata["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest())
        except (OSError, ValueError, KeyError):
            valid = False
        if not valid:
            write_sfx(directory, clip_id)
    return directory
