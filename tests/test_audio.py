"""Mixer injetável: testes sem SDL, placa de som ou janela."""

from pathlib import Path
from types import SimpleNamespace
import pytest

from vigilia.core.events import EventBus, SfxRequestedEvent, MusicChangeRequestedEvent
from vigilia.core.mathx import Vec3, Transform
from vigilia.combat.events import SfxRequestedEvent as CombatSfx, DamageDealt, ParrySucceeded
from vigilia.player.events import SfxRequestedEvent as PlayerSfx
from vigilia.engine.audio import AudioBackend, AudioEventRouter, Priority

ROOT = Path(__file__).resolve().parents[1]


class ChannelFake:
    def __init__(self):
        self.busy, self.sound, self.volume, self.stops = False, None, (), 0
    def play(self, sound, **kwargs):
        self.busy, self.sound, self.loops = True, sound, kwargs.get("loops", 0)
    def stop(self):
        self.busy = False
        self.stops += 1
    def get_busy(self):
        return self.busy
    def set_volume(self, *values):
        self.volume = values


class MixerFake:
    def __init__(self):
        self.channels, self.initialized = [], False
    def get_init(self):
        return self.initialized
    def init(self, **kwargs):
        self.initialized = True
    def set_num_channels(self, count):
        self.channels = [ChannelFake() for _ in range(count)]
    def set_reserved(self, count):
        self.reserved = count
    def Channel(self, index):
        return self.channels[index]
    def Sound(self, path):
        return Path(path).stem
    def quit(self):
        self.initialized = False


@pytest.fixture
def backend(tmp_path):
    for directory, clips in (("sfx", ("hit", "parry", "parry_spark", "ui_ping")),
                              ("music", ("a", "b", "c"))):
        folder = tmp_path / "audio" / directory
        folder.mkdir(parents=True)
        for name in clips:
            (folder / (name + ".wav")).write_bytes(b"fake")
    return AudioBackend(tmp_path, mixer=MixerFake())


def test_silent_without_assets_never_initializes_mixer(tmp_path):
    mixer = MixerFake()
    audio = AudioBackend(tmp_path, mixer=mixer)
    assert not audio.enabled and not mixer.initialized
    assert not audio.play_sfx("missing")
    audio.play_music("a")
    audio.stop_music()
    audio.update(1)
    audio.close()


def test_missing_device_is_silent_fallback(tmp_path):
    folder = tmp_path / "audio/sfx"
    folder.mkdir(parents=True)
    (folder / "hit.wav").write_bytes(b"fake")
    class Unavailable(MixerFake):
        def init(self, **kwargs):
            raise RuntimeError("no sound device")
    assert not AudioBackend(tmp_path, mixer=Unavailable()).enabled


def test_has_32_sfx_and_two_reserved_music_channels(backend):
    assert len(backend.voices) == 32
    assert backend._mixer.reserved == 2 and len(backend._mixer.channels) == 34


def test_canonical_event_and_three_simultaneous_parry_layers(backend):
    assert CombatSfx is PlayerSfx is SfxRequestedEvent
    bus = EventBus()
    AudioEventRouter(bus, backend, ROOT / "data/audio/map.toml")
    bus.publish(SfxRequestedEvent("parry"))
    assert [voice.channel.sound for voice in backend.voices if voice.channel.busy] == ["parry", "parry_spark", "ui_ping"]
    assert all(voice.channel.stops == 0 for voice in backend.voices)


def test_high_priority_steals_oldest_low_not_music(backend):
    backend.play_music("a", fade_sec=0)
    for _ in range(32):
        backend.play_sfx("hit", priority=Priority.LOW)
    assert backend.play_sfx("parry", priority=Priority.HIGH)
    assert backend.voices[0].channel.sound == "parry"
    assert backend._music[0].get_busy()


def test_low_does_not_interrupt_high(backend):
    for _ in range(32):
        backend.play_sfx("hit", priority=Priority.HIGH)
    assert not backend.play_sfx("parry", priority=Priority.LOW)


def test_critical_always_steals_oldest_even_if_all_critical(backend):
    for _ in range(32):
        backend.play_sfx("hit", priority=Priority.CRITICAL)
    assert backend.play_sfx("parry", priority=Priority.CRITICAL)
    assert backend.voices[0].channel.sound == "parry"


def test_finished_channel_reused_before_stealing(backend):
    backend.play_sfx("hit", priority=Priority.HIGH)
    backend.voices[0].channel.busy = False
    backend.play_sfx("parry", priority=Priority.LOW)
    assert backend.voices[0].channel.sound == "parry" and backend.voices[0].channel.stops == 0


def test_positional_attenuation_pan_and_live_volume(backend):
    backend.set_volumes(1, 1, 1)
    backend.set_listener(Vec3(), Vec3(1, 0))
    backend.play_sfx("hit", position=Vec3(10, 0))
    voice = backend.voices[0]
    assert voice.channel.volume == pytest.approx((0, .5))
    backend.set_listener(Vec3(30, 0), Vec3(1, 0))
    backend.update(0)
    assert voice.channel.volume == (0, 0)
    backend.set_listener(Vec3(20, 0), Vec3(1, 0))
    backend.set_volumes(.5, 1, .5)
    assert voice.channel.volume == pytest.approx((.125, 0))


def test_nonpositional_plays_both_channels_and_missing_clip_is_noop(backend):
    backend.set_volumes(1, 1, 1)
    assert backend.play_sfx("hit", gain=.4)
    assert backend.voices[0].channel.volume == (.4, .4)
    assert not backend.play_sfx("unknown")


def test_crossfade_keeps_both_tracks_then_releases_old(backend):
    backend.play_music("a", fade_sec=0)
    backend.play_music("b", fade_sec=1.5)
    backend.update(.75)
    assert backend._levels == pytest.approx([.5, .5])
    assert all(channel.busy for channel in backend._music)
    backend.update(.75)
    assert backend._levels == [0, 1] and not backend._music[0].busy
    assert backend._music[1].loops == -1


def test_rapid_track_changes_and_same_track_do_not_restart(backend):
    backend.play_music("a", fade_sec=0)
    backend.play_music("b")
    backend.update(.2)
    backend.play_music("c", fade_sec=.5)
    backend.update(.5)
    stops = [channel.stops for channel in backend._music]
    backend.play_music("c")
    assert [channel.stops for channel in backend._music] == stops
    assert backend._levels == [1, 0]


def test_stop_music_fades_to_silence_and_close_releases_device(backend):
    backend.play_music("a", fade_sec=0)
    backend.stop_music(fade_sec=1)
    backend.update(.5)
    assert backend._levels[0] == .5
    backend.update(.5)
    assert not any(channel.busy for channel in backend._music)
    backend.close()
    backend.close()
    assert not backend.enabled and not backend._mixer.initialized


def test_game_combat_events_request_sfx_and_matching_particles():
    from vigilia.game import Game
    from vigilia.entities.ecs import World
    from vigilia.combat.fighter import Fighter
    from vigilia.player.movesets import LONGSWORD
    game = Game.__new__(Game)
    game._bus, game._world = EventBus(), World()
    game._entity = game._world.spawn(Transform(Vec3(1, 2, 1)), Fighter(0, LONGSWORD.weapon))
    game._notify = lambda message: None
    effects, sounds = [], []
    game._particles = SimpleNamespace(spawn=lambda *args: effects.append(args))
    game._bus.subscribe(SfxRequestedEvent, sounds.append)
    for event, preset in ((DamageDealt(2, game._entity.id, 10, 90, False, ""), "blood"),
                           (DamageDealt(2, game._entity.id, 10, 80, False, "", "fire"), "embers"),
                           (DamageDealt(2, game._entity.id, 1, 79, True, ""), "sparks")):
        game._on_damage(event)
        assert effects[-1][0] == preset
    game._on_parry(ParrySucceeded(game._entity.id, 2))
    assert sounds[-1].kind == "parry" and effects[-1][0] == "sparks"


def test_game_music_handler_routes_stop_and_short_phase_fade():
    from vigilia.game import Game
    calls = []
    game = Game.__new__(Game)
    game._audio = SimpleNamespace(play_music=lambda *args, **kwargs: calls.append((args, kwargs)),
                                  stop_music=lambda **kwargs: calls.append(((), kwargs)))
    game._on_music(MusicChangeRequestedEvent("boss_phase2", .5))
    assert calls[-1] == (("boss_phase2",), {"fade_sec": .5})
    game._on_music(MusicChangeRequestedEvent("", 1))
    assert calls[-1] == ((), {"fade_sec": 1}) and game.music_track == ""
