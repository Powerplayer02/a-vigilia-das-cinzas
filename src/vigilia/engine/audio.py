"""Mixer opcional, canais prioritários e crossfade de dois loops pré-carregados."""

from dataclasses import dataclass
from enum import IntEnum
import logging
from pathlib import Path
import tomllib

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


class AudioBackend:
    """Não importa/inicializa pygame quando não há WAVs; erros deixam silêncio."""

    def __init__(self, assets: Path, *, mixer_hz: int = 44100, channels: int = 32,
                 mixer=None, music_directory: Path | None = None, music_loops=None,
                 music_clock=None) -> None:
        if channels < 1:
            raise ValueError("channels deve ser positivo")
        self.enabled = False
        self._closed = False
        self._owned = False
        self._mixer = mixer
        self._sounds = {}
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
            mixer.set_reserved(2)
            self._music = [mixer.Channel(0), mixer.Channel(1)]
            self.voices = [Voice(mixer.Channel(i + 2)) for i in range(channels)]
            for path in files:
                try:
                    sound = mixer.Sound(str(path))
                    (self._music_sounds if path.parent.name == "music" else self._sounds)[path.stem] = sound
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

    def play_sfx(self, clip_id: str, *, position: Vec3 | None = None,
                 priority: Priority = Priority.MEDIUM, gain: float = 1) -> bool:
        sound = self._sounds.get(clip_id)
        if not self.enabled or sound is None:
            return False
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
        self._duck_gain += (self._duck_target - self._duck_gain) * min(1., max(0., dt) / .15)
        self._fade_age = (max(0., self.music_clock() - self._fade_started)
                          if self.music_clock is not None else self._fade_age + max(0., dt))
        alpha = min(1., self._fade_age / self._fade_duration) if self._fade_duration else 1.
        for i, channel in enumerate(self._music):
            self._levels[i] = self._starts[i] + (self._targets[i] - self._starts[i]) * alpha
            channel.set_volume(self._levels[i] * self.master_volume * self.music_volume * self._duck_gain)
            if alpha == 1 and self._targets[i] == 0 and channel.get_busy():
                channel.stop()
        if (self._current >= 0 and self.track_id and not self._music_loops.get(self.track_id, True)
                and not self._music[self._current].get_busy()):
            self.music_finished = True
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
        bus.subscribe(SfxRequestedEvent, self.on_sfx)
        bus.subscribe(SettingsChangedEvent, self.on_settings)

    def on_settings(self, event):
        options = event.options
        self.backend.set_volumes(options.master_volume, options.music_volume, options.sfx_volume)

    def on_sfx(self, event: SfxRequestedEvent) -> None:
        preset = self.mapping.get(event.kind)
        if preset is None:
            return
        for clip in preset["clips"]:
            self.backend.play_sfx(clip, position=event.position,
                priority=Priority(preset["priority"]), gain=preset.get("gain", 1) * event.gain)
