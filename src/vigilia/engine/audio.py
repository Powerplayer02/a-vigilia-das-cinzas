"""Mixer opcional, canais prioritários e crossfade de dois loops pré-carregados."""

from dataclasses import dataclass
from enum import IntEnum
import logging
from pathlib import Path
import tomllib
import wave

from vigilia.core.events import EventBus, SfxRequestedEvent, SettingsChangedEvent
from vigilia.core.mathx import Vec3


class Priority(IntEnum):
    LOW = 0
    MEDIUM = 1
    HIGH = 2
    CRITICAL = 3


@dataclass(slots=True)
class Voice:
    channel: object
    priority: int = 0
    serial: int = 0
    position: Vec3 | None = None
    gain: float = 1
    bus: str = "combat"
    ui_reserved: bool = False
    peak: float = 1.
    mix_left: float = 0.
    mix_right: float = 0.
    mixing: bool = False


class AudioBackend:
    """Não importa/inicializa pygame quando não há WAVs; erros deixam silêncio."""

    def __init__(self, assets: Path, *, mixer_hz: int = 44100, channels: int = 32,
                 mixer=None, music_directory: Path | None = None, music_loops=None,
                 music_clock=None, sfx_directory: Path | None = None,
                 enhanced_sfx: bool = False, buses=None) -> None:
        if channels < 1:
            raise ValueError("channels deve ser positivo")
        if enhanced_sfx and channels < 4:
            raise ValueError("Categorized SFX requires at least four channels")
        self.enabled = False
        self._closed = False
        self._owned = False
        self._mixer = mixer
        self._sounds = {}
        self._sound_peaks = {}
        self._music_peak_max = 0.
        self.enhanced_sfx = enhanced_sfx
        self.buses = {name: 1. for name in ("combat", "ui", "ambient", "music")}
        if buses:
            self.buses.update(buses)
        if set(self.buses) != {"combat", "ui", "ambient", "music"} or any(
                type(value) not in (int, float) or not 0 <= value <= 1 for value in self.buses.values()):
            raise ValueError("Audio bus gains must be finite values from 0 to 1")
        self._music_guard = 1.
        self._sfx_budget = .78
        self._music_sounds = {}
        self.voices = []
        self._music = []
        self._levels = [0.0, 0.0]
        self._starts = [0.0, 0.0]
        self._targets = [0.0, 0.0]
        self._fade_age = self._fade_duration = 0.0
        self._current = -1
        self.track_id = ""
        self.music_finished = False
        self._music_loops = music_loops or {}
        self._duck_gain = self._duck_target = 1.
        self.music_clock = music_clock
        self._fade_started = music_clock() if music_clock else 0.
        self._serial = 0
        self.listener, self.right = Vec3(), Vec3(1, 0)
        self.master_volume, self.music_volume, self.sfx_volume = 1.0, .6, .8
        files = list((assets / "audio").glob("*/*.wav"))
        if music_directory is not None:
            generated = list(music_directory.glob("*.wav"))
            names = {path.stem for path in generated}
            files = [path for path in files if path.parent.name != "music" or path.stem not in names]
            files += generated
        if sfx_directory is not None:
            generated = list(sfx_directory.glob("*.wav"))
            names = {path.stem for path in generated}
            files = [path for path in files if path.parent.name != "sfx" or path.stem not in names]
            files += generated
        if not files:
            return
        try:
            if mixer is None:
                import pygame.mixer as mixer
            self._mixer = mixer
            if not mixer.get_init():
                mixer.init(frequency=mixer_hz, size=-16, channels=2, buffer=512)
                self._owned = True
            mixer.set_num_channels(channels + 2)
            ui_count = min(2, max(1, channels // 4)) if enhanced_sfx and channels >= 2 else 0
            mixer.set_reserved(2 + ui_count)
            self._music = [mixer.Channel(0), mixer.Channel(1)]
            self.voices = [Voice(mixer.Channel(i + 2), ui_reserved=i < ui_count) for i in range(channels)]
            for path in files:
                try:
                    sound = mixer.Sound(str(path))
                    is_music = path.parent.name == "music" or path.parent == music_directory
                    (self._music_sounds if is_music else self._sounds)[path.stem] = sound
                    if enhanced_sfx:
                        peak = self._pcm_peak(path)
                        if is_music:
                            self._music_peak_max = max(self._music_peak_max, peak)
                        else:
                            self._sound_peaks[path.stem] = peak
                except Exception as error:
                    logging.getLogger(__name__).warning("Áudio ignorado %s: %s", path.name, error)
            self.enabled = True
            if music_directory is not None and "furnace_ambient" in self._music_sounds:
                self._music_sounds["forge_ambient"] = self._music_sounds["furnace_ambient"]
        except Exception as error:
            logging.getLogger(__name__).warning("Áudio indisponível, continuando em silêncio: %s", error)
            self.close()

    def set_listener(self, position: Vec3, right: Vec3) -> None:
        self.listener, self.right = position, right.flat().normalized()

    def set_volumes(self, master: float, music: float, sfx: float) -> None:
        self.master_volume, self.music_volume, self.sfx_volume = (
            max(0., min(1., value)) for value in (master, music, sfx))
        self.update(0)

    def _volume(self, voice: Voice) -> None:
        gain = voice.gain * self.master_volume * self.sfx_volume
        pan = 0.0
        if voice.position is not None:
            delta = voice.position - self.listener
            distance = delta.length()
            gain *= max(0., 1 - distance / 20)
            pan = delta.normalized().dot(self.right)
        voice.channel.set_volume(gain * min(1., 1 - pan), gain * min(1., 1 + pan))

    @staticmethod
    def _pcm_peak(path):
        """Once at load, never on a gameplay frame; unknown assets use worst case."""
        try:
            import numpy as np
            with wave.open(str(path)) as stream:
                if stream.getsampwidth() != 2:
                    return 1.
                peak = 0
                while data := stream.readframes(65536):
                    peak = max(peak, int(np.abs(np.frombuffer(data, dtype="<i2").astype(np.int32)).max()))
            return peak / 32768
        except (OSError, EOFError, wave.Error):
            return 1.

    def _mix_sfx(self, include=None):
        """Peak-aware L1 bound leaves at least 2 dB plus mixer quantization room.

        UI channels cannot be stolen by combat. UI gets its own share while
        ambient sounds duck under foreground cues. No waveform processing here.
        """
        music_bound = self._music_peak_max * self.music_volume * self.buses["music"]
        self._music_guard = min(1., .55 / music_bound) if music_bound else 1.
        self._sfx_budget = .78 - music_bound * self._music_guard
        ui_live = combat_live = False
        for voice in self.voices:
            voice.mixing = voice is include or voice.channel.get_busy()
            if voice.mixing:
                ui_live |= voice.bus == "ui"
                combat_live |= voice.bus == "combat" and voice.priority >= 40
        ui_sum = shared_sum = 0.
        for voice in self.voices:
            if not voice.mixing:
                continue
            gain = min(1., max(0., voice.gain)) * self.buses[voice.bus]
            if voice.bus == "ambient" and (ui_live or combat_live):
                gain *= .25
            elif voice.bus == "combat" and ui_live:
                gain *= .8
            pan = 0.
            if voice.position is not None:
                delta = voice.position - self.listener
                gain *= max(0., 1 - delta.length() / 20)
                pan = delta.normalized().dot(self.right)
            voice.mix_left, voice.mix_right = gain * min(1., 1 - pan), gain * min(1., 1 + pan)
            bound = max(voice.mix_left, voice.mix_right) * voice.peak
            if voice.bus == "ui":
                ui_sum += bound
            else:
                shared_sum += bound
        ui_budget = min(ui_sum, self._sfx_budget * .38) if ui_live else 0.
        ui_scale = min(1., ui_budget / ui_sum) if ui_sum else 1.
        shared_scale = min(1., (self._sfx_budget - ui_budget) / shared_sum) if shared_sum else 1.
        for voice in self.voices:
            if voice.mixing:
                scale = (ui_scale if voice.bus == "ui" else shared_scale) * self.master_volume * self.sfx_volume
                voice.channel.set_volume(voice.mix_left * scale, voice.mix_right * scale)

    def play_sfx(self, clip_id: str, *, position: Vec3 | None = None,
                 priority: Priority = Priority.MEDIUM, gain: float = 1, bus: str = "combat") -> bool:
        sound = self._sounds.get(clip_id)
        if not self.enabled or sound is None:
            return False
        if self.enhanced_sfx:
            return self._play_categorized(sound, clip_id, position, priority, gain, bus)
        voice = next((voice for voice in self.voices if not voice.channel.get_busy()), None)
        if voice is None:
            eligible = [voice for voice in self.voices if voice.priority < priority]
            if priority == Priority.CRITICAL and not eligible:
                eligible = self.voices
            if not eligible:
                return False
            voice = min(eligible, key=lambda item: (item.priority, item.serial))
            voice.channel.stop()
        self._serial += 1
        voice.priority, voice.serial, voice.position, voice.gain = priority, self._serial, position, gain
        # Volume antes de play evita um bloco audível no volume do ocupante anterior.
        self._volume(voice)
        voice.channel.play(sound)
        return True

    def _play_categorized(self, sound, clip_id, position, priority, gain, bus):
        if bus not in ("combat", "ui", "ambient"):
            raise ValueError("Unknown SFX bus")
        pool = [voice for voice in self.voices if voice.ui_reserved == (bus == "ui")]
        if not pool:
            return False
        voice = next((voice for voice in pool if not voice.channel.get_busy()), None)
        if voice is None:
            order = {"ambient": 0, "combat": 1, "ui": 2}
            score = (order[bus], priority)
            eligible = [voice for voice in pool if (order[voice.bus], voice.priority) <= score]
            if not eligible:
                return False
            voice = min(eligible, key=lambda row: (order[row.bus], row.priority, row.serial))
            voice.channel.stop()
        self._serial += 1
        voice.priority, voice.serial, voice.position = priority, self._serial, position
        voice.gain, voice.bus, voice.peak = gain, bus, self._sound_peaks.get(clip_id, 1.)
        # Rebalance all channels before play: no block at the old occupant's gain.
        self._mix_sfx(include=voice)
        voice.channel.play(sound)
        return True

    def _fade(self, targets, fade_sec):
        self._starts = self._levels.copy()
        self._targets = targets
        self._fade_age, self._fade_duration = 0., max(0., fade_sec)
        if self.music_clock is not None:
            self._fade_started = self.music_clock()
        self.update(0)

    def play_music(self, track_id: str, *, fade_sec: float = 1.5) -> None:
        if track_id == self.track_id:
            return
        self.track_id = track_id
        self.music_finished = False
        if not self.enabled:
            return
        sound = self._music_sounds.get(track_id)
        if sound is None:
            self._fade([0., 0.], fade_sec)
            return
        index = 0 if self._current < 0 else 1 - self._current
        # Mudança rápida substitui o lado que estava saindo, preserva o atual.
        self._music[index].stop()
        self._levels[index] = 0.
        self._music[index].set_volume(0.)
        self._music[index].play(sound, loops=-1 if self._music_loops.get(track_id, True) else 0)
        self._current = index
        self._fade([1. if i == index else 0. for i in range(2)], fade_sec)

    def stop_music(self, *, fade_sec: float = 1.0) -> None:
        self.track_id = ""
        self.music_finished = False
        self._fade([0., 0.], fade_sec)

    def set_music_duck(self, decibels: float) -> None:
        self._duck_target = 10 ** (min(0., decibels) / 20)

    def update(self, dt: float) -> None:
        if not self.enabled:
            return
        if self.enhanced_sfx:
            self._mix_sfx()
        self._duck_gain += (self._duck_target - self._duck_gain) * min(1., max(0., dt) / .15)
        self._fade_age = (max(0., self.music_clock() - self._fade_started)
                          if self.music_clock is not None else self._fade_age + max(0., dt))
        alpha = min(1., self._fade_age / self._fade_duration) if self._fade_duration else 1.
        for i, channel in enumerate(self._music):
            self._levels[i] = self._starts[i] + (self._targets[i] - self._starts[i]) * alpha
            channel.set_volume(self._levels[i] * self.master_volume * self.music_volume * self._duck_gain
                               * (self.buses["music"] * self._music_guard if self.enhanced_sfx else 1.))
            if alpha == 1 and self._targets[i] == 0 and channel.get_busy():
                channel.stop()
        if (self._current >= 0 and self.track_id and not self._music_loops.get(self.track_id, True)
                and not self._music[self._current].get_busy()):
            self.music_finished = True
        if not self.enhanced_sfx:
            for voice in self.voices:
                if voice.channel.get_busy():
                    self._volume(voice)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for channel in self._music:
            channel.stop()
        for voice in self.voices:
            voice.channel.stop()
        if self._owned:
            self._mixer.quit()
            self._owned = False
        self.enabled = False


class AudioEventRouter:
    """Traduz apenas o evento canônico; presets podem conter várias camadas."""

    def __init__(self, bus: EventBus, backend, mapping: Path) -> None:
        self.backend = backend
        self.mapping = tomllib.loads(mapping.read_text(encoding="utf-8")) if mapping.exists() else {}
        self._variants = {}
        bus.subscribe(SfxRequestedEvent, self.on_sfx)
        bus.subscribe(SettingsChangedEvent, self.on_settings)

    def on_settings(self, event):
        options = event.options
        self.backend.set_volumes(options.master_volume, options.music_volume, options.sfx_volume)

    def on_sfx(self, event: SfxRequestedEvent) -> None:
        preset = self.mapping.get(event.kind)
        if preset is None:
            return
        if variants := preset.get("variants"):
            index = self._variants.get(event.kind, 0)
            clips = [variants[index % len(variants)]]
            self._variants[event.kind] = index + 1
        else:
            clips = preset["clips"]
        for clip in clips:
            options = {"bus": preset["bus"]} if "bus" in preset else {}
            self.backend.play_sfx(clip, position=event.position,
                priority=preset["priority"], gain=preset.get("gain", 1) * event.gain, **options)
