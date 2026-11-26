"""Each generated cue through its real event router, protected pools and peak guard."""

from dataclasses import replace
import hashlib
from pathlib import Path
import tomllib
import wave

import numpy as np
import pytest

from vigilia.core.events import EventBus, SfxRequestedEvent
from vigilia.engine.audio import AudioBackend, AudioEventRouter
from vigilia.engine.sfx_synthesis import SPECS, PRESETS, synthesize, write_sfx
from test_audio import MixerFake

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def assets(tmp_path_factory):
    root = tmp_path_factory.mktemp("sfx-pool")
    directory = root / "sfx"
    directory.mkdir()
    for name in SPECS:
        (directory / (name + ".wav")).write_bytes(b"fake")
    music = root / "audio/music"
    music.mkdir(parents=True)
    (music / "theme.wav").write_bytes(b"fake")
    return root


@pytest.fixture
def audio(assets):
    return AudioBackend(assets, mixer=MixerFake(), channels=8, enhanced_sfx=True,
        sfx_directory=assets / "sfx", buses={"combat": 1, "ui": .9, "ambient": .6, "music": .7})


@pytest.mark.parametrize("clip_id", sorted(SPECS))
def test_each_sfx_routes_to_correct_pool_and_preempts_lower_priority(audio, clip_id):
    kind, preset = next((key, value) for key, value in PRESETS.items() if clip_id in value["variants"])
    pool = [voice for voice in audio.voices if voice.ui_reserved == (preset["bus"] == "ui")]
    for _ in pool:
        assert audio.play_sfx("hit_flesh", bus=preset["bus"], priority=preset["priority"] - 1)
    previous = {id(voice): voice.channel.stops for voice in pool}
    bus = EventBus()
    router = AudioEventRouter(bus, audio, ROOT / "data/audio/sfx.toml")
    router._variants[kind] = preset["variants"].index(clip_id)
    bus.publish(SfxRequestedEvent(kind))
    chosen = next(voice for voice in audio.voices if voice.serial == audio._serial)
    assert chosen.channel.sound == clip_id
    assert chosen.ui_reserved == (preset["bus"] == "ui")
    assert chosen.bus == preset["bus"] and chosen.priority == preset["priority"]
    assert chosen.channel.stops == previous[id(chosen)] + 1
    assert max(chosen.channel.volume) > 0


def test_phase_roar_death_parry_hit_and_footstep_have_strict_order(audio):
    rank = [PRESETS[k]["priority"] for k in ("boss_phase2", "boss_death", "parry", "hit_flesh", "footstep_stone")]
    assert rank == sorted(rank, reverse=True) and len(set(rank)) == 5
    for _ in range(6):
        assert audio.play_sfx("boss_phase2", priority=rank[0])
    for key, priority in zip(("boss_death", "parry", "hit_flesh", "footstep_stone_1"), rank[1:]):
        assert not audio.play_sfx(key, priority=priority)
    assert audio.play_sfx("ui_confirm", bus="ui", priority=60)
    assert audio.play_sfx("ui_error", bus="ui", priority=60)
    assert all(voice.channel.get_busy() for voice in audio.voices)
    assert sum(voice.ui_reserved for voice in audio.voices) == 2


def test_combat_cannot_take_ui_channels_or_music_and_ambient_loses(audio):
    audio.play_music("theme", fade_sec=0)
    audio.play_sfx("ui_confirm", bus="ui", priority=60)
    ui = next(v for v in audio.voices if v.bus == "ui" and v.channel.get_busy())
    for _ in range(6):
        audio.play_sfx("bonfire_ambient", bus="ambient", priority=15)
    assert audio.play_sfx("footstep_stone_1", priority=10)
    for _ in range(6):
        assert audio.play_sfx("boss_phase2", priority=95)
    assert ui.channel.sound == "ui_confirm" and ui.channel.stops == 0
    assert audio._music[0].sound == "theme" and audio._music[0].get_busy()
    assert not audio.play_sfx("bonfire_ambient", bus="ambient", priority=1000)


def test_live_mix_bound_at_full_sliders_includes_music_and_eight_voices(audio):
    audio.set_volumes(1, 1, 1)
    audio.play_music("theme", fade_sec=0)
    for _ in range(6):
        audio.play_sfx("hit_flesh", priority=40, gain=1)
    for _ in range(2):
        audio.play_sfx("ui_confirm", bus="ui", priority=60, gain=1)
    audio.update(.01)
    bound = max(sum(voice.channel.volume[channel] * voice.peak for voice in audio.voices) for channel in (0, 1))
    bound += sum(max(channel.volume) * audio._music_peak_max for channel in audio._music)
    assert bound <= .780001 < 10 ** (-1 / 20)
    audio.set_volumes(.5, .4, .3)
    assert all(max(v.channel.volume) <= .5 for v in audio.voices)


def test_weapon_variants_cycle_instead_of_playing_all_at_once(audio):
    bus = EventBus()
    AudioEventRouter(bus, audio, ROOT / "data/audio/sfx.toml")
    sounds = []
    for _ in range(4):
        bus.publish(SfxRequestedEvent("katana_light"))
        sounds.append(next(v.channel.sound for v in audio.voices if v.serial == audio._serial))
    assert sounds == ["katana_light_1", "katana_light_2", "katana_light_3", "katana_light_1"]


@pytest.mark.parametrize("clip_id", sorted(SPECS))
def test_every_generated_asset_has_headroom_and_short_feedback(clip_id):
    pcm = synthesize(clip_id)
    spec = SPECS[clip_id]
    assert pcm.shape == (round(spec.duration * 44100), 2)
    peak = np.abs(pcm.astype(np.int32)).max() / 32768
    assert 0 < peak <= 10 ** (-1 / 20)
    assert not np.any(pcm[0]) and not np.any(pcm[-1])
    if spec.family == "ui":
        assert spec.duration <= .2
    elif spec.family != "roar" and not clip_id.startswith(("bonfire", "area_", "shortcut", "door_", "fog_", "chest_", "item_pickup")):
        assert spec.duration <= .4


def test_seed_format_cache_repair_and_catalogue_consistency(tmp_path, monkeypatch):
    from vigilia.engine import sfx_synthesis as generator
    a = synthesize("parry", 5)
    assert hashlib.sha256(a.tobytes()).hexdigest() == "b118edd9955cf1fd4d27de33b78134db9b47aa59589ce6b3e3ade5b06b2e804f"
    assert np.array_equal(a, synthesize("parry", 5))
    assert not np.array_equal(a, synthesize("parry", 6))
    path, report = write_sfx(tmp_path, "parry", 5)
    with wave.open(str(path)) as stream:
        assert (stream.getframerate(), stream.getnchannels(), stream.getsampwidth()) == (44100, 2, 2)
    assert report["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(generator, "SPECS", {"parry": SPECS["parry"]})
    generator.ensure_sfx(tmp_path)
    canonical = path.read_bytes()
    path.write_bytes(b"corrupt")
    generator.ensure_sfx(tmp_path)
    assert path.read_bytes() == canonical
    assert tomllib.loads((ROOT / "data/audio/sfx.toml").read_text()) == PRESETS


def test_invalid_bus_gains_and_too_small_protected_pool(assets):
    for value in (-1, 2, float("nan"), True):
        with pytest.raises(ValueError):
            AudioBackend(assets, mixer=MixerFake(), enhanced_sfx=True, buses={"ui": value})
    with pytest.raises(ValueError):
        AudioBackend(assets, enhanced_sfx=True, channels=1)


def test_project_bus_configuration_rejects_invalid_values(tmp_path):
    from vigilia.core.config import load_config
    path = tmp_path / "config.toml"
    path.write_text('[audio]\nprocedural_sfx = true\n[audio.buses]\ncombat = 1.0\nui = 0.9\nambient = 0.6\nmusic = 0.7\n')
    config = load_config(path)
    assert config.procedural_sfx and config.audio_buses["ui"] == .9
    path.write_text('[audio.buses]\nui = 1.1\n')
    with pytest.raises(ValueError):
        load_config(path)
