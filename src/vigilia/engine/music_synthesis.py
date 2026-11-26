"""Original seeded score; offline NumPy synthesis and PCM WAV cache.

No device or renderer is initialized here. Generation never runs in gameplay.
Loudness uses the BS.1770 stereo gates and a frequency-domain K filter;
the loop is treated as periodic rather than having a filter startup transient.
"""

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import tempfile
import wave

import numpy as np

VERSION = 1
SAMPLE_RATE = 44100


@dataclass(frozen=True)
class Track:
    duration: int
    root: int
    palette: str
    motif: tuple[int, ...] = (0, 7, 3, 2, 0, -2)
    phase: int = 1
    loop: bool = True


TRACKS = {
    "patio_ambient": Track(96, 50, "wind"),
    "cathedral_ambient": Track(96, 48, "organ", (0, 3, 7, 10, 7, 2)),
    "marsh_ambient": Track(96, 50, "strings", (0, 1, 7, 6, 3, 1)),
    "ruins_ambient": Track(96, 48, "stone", (0, 7, 10, 3, 2, 0)),
    "furnace_ambient": Track(96, 41, "brass", (0, 7, 8, 3, 2, 0)),
    "boss_phase1": Track(96, 38, "boss", (0, 7, 3, 2, 8, 7)),
    "boss_phase2": Track(96, 38, "boss", (0, 7, 3, 2, 8, 7), 2),
    "tide_boss_phase1": Track(96, 48, "tide", (0, 1, 7, 10, 8, 3)),
    "tide_boss_phase2": Track(96, 48, "tide", (0, 1, 7, 10, 8, 3), 2),
    "cinder_boss_phase1": Track(96, 41, "cinder", (0, 7, 8, 2, 3, -1)),
    "cinder_boss_phase2": Track(96, 41, "cinder", (0, 7, 8, 2, 3, -1), 2),
    "cinder_boss_phase3": Track(96, 41, "cinder", (0, 7, 8, 2, 3, -1), 3),
    "menu_theme": Track(30, 50, "menu"),
    "ending_maintain": Track(60, 50, "brass", loop=False),
    "ending_extinguish": Track(60, 48, "strings", loop=False),
    "ending_transform": Track(60, 50, "dawn", (0, 4, 7, 11, 9, 7), loop=False),
    "post_credits": Track(30, 50, "dawn", loop=False),
}
ALIASES = {"forge_ambient": "furnace_ambient"}


def seed_for(track_id: str) -> int:
    return int.from_bytes(hashlib.sha256(track_id.encode("utf8")).digest()[:8], "little")


def _wrap_add(output, sound, start, pan, gain, rate):
    """Wrap note releases/reverb across the seam, without an index array."""
    offset = round(start * rate) % len(output)
    gains = (math.sqrt((1 - pan) * .5) * gain, math.sqrt((1 + pan) * .5) * gain)
    cursor = 0
    while cursor < len(sound):
        count = min(len(sound) - cursor, len(output) - offset)
        for channel, level in enumerate(gains):
            output[offset:offset + count, channel] += sound[cursor:cursor + count] * level
        cursor += count
        offset = 0


def _note(midi, seconds, kind, rate, rng):
    count = round(seconds * rate)
    t = np.arange(count, dtype=np.float64) / rate
    frequency = 440 * 2 ** ((midi - 69) / 12)
    if kind == "pluck":
        # Karplusâ€“Strong recurrence, evaluated in delay-sized vector blocks.
        delay = max(4, round(rate / frequency))
        signal = np.zeros(count + delay + 1)
        signal[:delay + 1] = rng.uniform(-1, 1, delay + 1)
        for offset in range(delay + 1, len(signal), delay):
            size = min(delay, len(signal) - offset)
            signal[offset:offset + size] = .993 * .5 * (
                signal[offset - delay:offset - delay + size] +
                signal[offset - delay - 1:offset - delay - 1 + size])
        sound = signal[delay + 1:]
        sound *= np.exp(-t * 1.1)
    else:
        harmonics = {"choir": (1, .08, .23, .09, .04),
                     "organ": (1, .5, .3, .12, .08),
                     "brass": (1, .42, .22, .12, .07),
                     "bass": (1, .12, .05),
                     "strings": (1, .35, .18, .10)}[kind]
        sound = np.zeros(count)
        for harmonic, level in enumerate(harmonics, 1):
            if frequency * harmonic < rate * .45:
                vibrato = .007 * np.sin(2 * np.pi * 4.7 * t) if kind in ("choir", "strings") else 0
                sound += level * np.sin(2 * np.pi * frequency * harmonic * t + vibrato)
        if kind == "brass":
            sound *= .7 + .3 * np.exp(-t * 2)
    attack = .012 if kind == "pluck" else min(1.8, seconds * .22)
    release = min(2.4, seconds * .4)
    envelope = np.minimum(1, t / attack) * np.minimum(1, (seconds - t) / release)
    sound *= np.sin(np.clip(envelope, 0, 1) * np.pi / 2) ** 2
    return sound.astype(np.float32)


def _k_response(size, rate):
    # Bilinear De Man parameters for the BS.1770 shelf and RLB high pass.
    z = np.exp(-2j * np.pi * np.fft.rfftfreq(size, 1 / rate) / rate)
    k = math.tan(math.pi * 1681.974450955533 / rate)
    vh = 10 ** (3.999843853973347 / 20)
    vb = vh ** .4996667741545416
    q = .7071752369554196
    a0 = 1 + k / q + k * k
    b = np.array((vh + vb * k / q + k * k, 2 * (k * k - vh), vh - vb * k / q + k * k)) / a0
    a = (1, 2 * (k * k - 1) / a0, (1 - k / q + k * k) / a0)
    response = (b[0] + b[1] * z + b[2] * z * z) / (a[0] + a[1] * z + a[2] * z * z)
    k = math.tan(math.pi * 38.13547087602444 / rate)
    q = .5003270373238773
    a0 = 1 + k / q + k * k
    a = (1, 2 * (k * k - 1) / a0, (1 - k / q + k * k) / a0)
    return response * (1 - 2 * z + z * z) / (1 + a[1] * z + a[2] * z * z)


def integrated_lufs(audio, rate=SAMPLE_RATE):
    if len(audio) < round(rate * .4):
        raise ValueError("Loudness requires at least 400 ms")
    response = _k_response(len(audio), rate)
    energy = np.zeros(len(audio))
    for channel in range(2):
        weighted = np.fft.irfft(np.fft.rfft(audio[:, channel]) * response, n=len(audio))
        energy += weighted * weighted
    cumulative = np.concatenate(([0.], np.cumsum(energy)))
    width, hop = round(rate * .4), round(rate * .1)
    starts = np.arange(0, len(audio) - width + 1, hop)
    powers = (cumulative[starts + width] - cumulative[starts]) / width
    absolute = powers[powers > 10 ** ((-70 + .691) / 10)]
    if not len(absolute):
        return float("-inf")
    gated = absolute[absolute >= absolute.mean() * .1]
    return float(-.691 + 10 * np.log10(gated.mean()))


def synthesize(track_id, seed=None, *, rate=SAMPLE_RATE, duration=None):
    track_id = ALIASES.get(track_id, track_id)
    track = TRACKS[track_id]
    seconds = track.duration if duration is None else float(duration)
    if rate < 8000 or seconds < .5 or seconds > 180:
        raise ValueError("Use 8 kHz or higher, duration 0.5â€“180 s")
    rng = np.random.Generator(np.random.PCG64(seed_for(track_id) if seed is None else seed))
    count = round(seconds * rate)
    output = np.zeros((count, 2), dtype=np.float32)
    boss = track.palette in ("boss", "tide", "cinder")
    chord_seconds = seconds / 4
    pad = {"organ": "organ", "strings": "strings", "brass": "brass", "cinder": "brass"}.get(track.palette, "choir")
    harmony = ((0, 3, 7), (8, 12, 15), (5, 8, 12), (10, 14, 17))
    if track.palette == "dawn":
        harmony = ((0, 4, 7), (5, 9, 12), (9, 12, 16), (7, 11, 14))
    for bar, chord in enumerate(harmony):
        for voice, interval in enumerate(chord):
            sound = _note(track.root + interval, chord_seconds + min(4, seconds / 8), pad, rate, rng)
            _wrap_add(output, sound, bar * chord_seconds - min(2, seconds / 16), (voice - 1) * .55, .10, rate)
        bass = _note(track.root - 12 + chord[0], chord_seconds + .5, "bass", rate, rng)
        _wrap_add(output, bass, bar * chord_seconds, 0, .10, rate)
    # Periodic wind/breath/fire: low-passed noise with slow, seamless modulation.
    noise = rng.normal(0, 1, count)
    frequencies = np.fft.rfftfreq(count, 1 / rate)
    spectrum = np.fft.rfft(noise)
    spectrum *= (1 - np.exp(-(frequencies / 80) ** 2)) / np.sqrt(1 + (frequencies / 650) ** 6)
    wind = np.fft.irfft(spectrum, n=count)
    wind /= max(1e-8, np.std(wind))
    t = np.arange(count) / rate
    breath = .7 + .2 * np.sin(2 * np.pi * t * 3 / seconds) + .1 * np.sin(2 * np.pi * t * 7 / seconds)
    wind_gain = .013 if track.palette in ("wind", "strings", "brass", "cinder") else .003
    output[:, 0] += (wind * breath * wind_gain).astype(np.float32)
    output[:, 1] += np.roll((wind * breath * wind_gain).astype(np.float32), round(rate * .017))
    # Each boss keeps the same six-note motif across all phases.
    phrase = seconds / (8 if boss else 4)
    for section in range(8 if boss else 4):
        for index, interval in enumerate(track.motif):
            if not boss and index % 2 and track.palette == "wind":
                continue
            start = section * phrase + phrase * (index + .3) / 8
            instrument = "brass" if boss and track.phase > 1 else "pluck"
            note = _note(track.root + 12 + interval, min(2.7, phrase / 3), instrument, rate, rng)
            _wrap_add(output, note, start, -.35 if index % 2 else .35, .045 if not boss else .065, rate)
    if boss or track.palette in ("stone", "brass"):
        beats = (64 + (track.phase - 1) * 32) if boss else 32
        for beat in range(beats):
            tdrum = np.arange(round(rate * .6)) / rate
            drum = np.sin(2 * np.pi * (43 * tdrum + 9 * (1 - np.exp(-tdrum * 24)))) * np.exp(-tdrum * 10)
            drum += rng.normal(0, .12, len(drum)) * np.exp(-tdrum * 35)
            drum *= np.minimum(1, tdrum / .004)
            _wrap_add(output, drum.astype(np.float32), beat * seconds / beats, 0, .08 if beat % 4 else .15, rate)
    dry = output.copy()
    for delay, gain in ((.29, .17), (.43, .13), (.71, .09), (1.09, .07)):
        output += np.roll(dry[:, ::-1], round(rate * delay), axis=0) * gain
    if not track.loop:
        output *= np.minimum(1, t / 2)[:, None]
        output *= np.minimum(1, (seconds - t) / min(5, seconds / 4))[:, None]
    else:
        # Remove the final sample discontinuity without fading the loop to silence.
        width = min(round(rate * .01), count)
        output[-width:] += np.linspace(0, 1, width)[:, None] * (output[0] - output[-1])
    # Gentle offline saturation bounds the crest factor before normalization.
    output = np.tanh(output * 2)
    for _ in range(4):
        gain = 10 ** ((-18 - integrated_lufs(output, rate)) / 20)
        output *= round(gain, 8)
        if np.max(np.abs(output)) <= .89:
            break
        output = np.tanh(output / .6) * .6
    if np.max(np.abs(output)) > .99:
        raise ValueError("Score exceeds PCM headroom")
    pcm = np.rint(np.round(output.astype(np.float64), 7) * 32767).astype("<i2")
    return pcm


def write_track(directory: Path, track_id: str, seed=None, *, rate=SAMPLE_RATE, duration=None):
    directory = Path(directory)
    track_id = ALIASES.get(track_id, track_id)
    if track_id not in TRACKS:
        raise ValueError("Unknown music track: " + track_id)
    seed = seed_for(track_id) if seed is None else seed
    pcm = synthesize(track_id, seed, rate=rate, duration=duration)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (track_id + ".wav")
    with tempfile.NamedTemporaryFile(dir=directory, suffix=".wav.tmp", delete=False) as tmp:
        temporary = Path(tmp.name)
    try:
        with wave.open(str(temporary), "wb") as stream:
            stream.setnchannels(2)
            stream.setsampwidth(2)
            stream.setframerate(rate)
            stream.writeframes(pcm.tobytes())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    report = dict(version=VERSION, track_id=track_id, seed=seed, sample_rate=rate,
                  duration=len(pcm) / rate, loop=TRACKS[track_id].loop,
                  integrated_lufs=round(integrated_lufs(pcm.astype(np.float64) / 32768, rate), 3),
                  sample_peak_dbfs=round(20 * math.log10(max(1, np.abs(pcm.astype(np.int32)).max()) / 32768), 3),
                  sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    path.with_suffix(".json").write_text(json.dumps(report, indent=2), encoding="utf8")
    return path, report


def ensure_score(directory: Path):
    """Called once before AudioBackend construction, never during a frame."""
    directory = Path(directory)
    for track_id in TRACKS:
        path = directory / (track_id + ".wav")
        metadata = path.with_suffix(".json")
        try:
            cached = json.loads(metadata.read_text(encoding="utf8"))
            valid = (cached["version"] == VERSION and cached["seed"] == seed_for(track_id)
                     and cached["duration"] == TRACKS[track_id].duration
                     and cached["sample_rate"] == SAMPLE_RATE
                     and cached["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest())
        except (OSError, ValueError, KeyError):
            valid = False
        if not valid:
            write_track(directory, track_id)
    return directory
