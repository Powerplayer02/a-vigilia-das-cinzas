"""Score and event sequencing without a window, SDL or a playback device."""

import hashlib
from pathlib import Path
import wave

import numpy as np
import pytest

from vigilia.core.events import MusicChangeRequestedEvent
from vigilia.engine.music import MusicDirector
from vigilia.engine.music_synthesis import (
    TRACKS, integrated_lufs, seed_for, synthesize, write_track,
)
from vigilia.engine.audio import AudioBackend
from test_audio import MixerFake


@pytest.fixture
def audio(tmp_path):
    folder = tmp_path / "music"
    folder.mkdir()
    for key in TRACKS:
        (folder / (key + ".wav")).write_bytes(b"fake")
    return AudioBackend(tmp_path, mixer=MixerFake(), music_directory=folder,
                        music_loops={key: track.loop for key, track in TRACKS.items()})


def test_two_area_events_crossfade_for_1500ms_and_release_outgoing(audio):
    director = MusicDirector(audio)
    director.request(MusicChangeRequestedEvent("patio_ambient", 0))
    director.request(MusicChangeRequestedEvent("cathedral_ambient"))
    audio.update(.75)
    assert audio._levels == pytest.approx([.5, .5])
    assert all(channel.get_busy() for channel in audio._music)
    audio.update(.75)
    assert audio._levels == [0, 1]
    assert not audio._music[0].get_busy()


def test_fog_out_half_second_then_one_second_boss_fade_and_phase_two(audio):
    director = MusicDirector(audio)
    director.request(MusicChangeRequestedEvent("patio_ambient", 0))
    director.request(MusicChangeRequestedEvent("boss_phase1"))
    audio.update(.25)
    director.update(.25)
    assert audio.track_id == "" and audio._levels[0] == pytest.approx(.5)
    director.request(MusicChangeRequestedEvent("boss_phase1"))  # no delay restart
    audio.update(.25)
    director.update(.25)
    assert audio.track_id == "boss_phase1"
    audio.update(.5)
    assert audio._levels[1] == pytest.approx(.5)
    audio.update(.5)
    director.request(MusicChangeRequestedEvent("boss_phase2", .5))
    assert audio._fade_duration == 2
    audio.update(2)
    assert audio.track_id == "boss_phase2" and audio._levels == [1, 0]


def test_new_area_or_stop_cancels_pending_boss_after_fog(audio):
    director = MusicDirector(audio)
    director.request(MusicChangeRequestedEvent("boss_phase1"))
    director.request(MusicChangeRequestedEvent("cathedral_ambient"))
    director.update(1)
    assert audio.track_id == "cathedral_ambient"
    director.request(MusicChangeRequestedEvent("boss_phase1"))
    director.request(MusicChangeRequestedEvent("", 3))
    director.update(1)
    assert audio.track_id == "" and audio._fade_duration == 3


def test_options_duck_minus6db_without_restart_and_restore_volumes(audio):
    audio.set_volumes(.8, .7, 1)
    director = MusicDirector(audio)
    director.request(MusicChangeRequestedEvent("patio_ambient", 0))
    sound = audio._music[0].sound
    stops = audio._music[0].stops
    director.set_options(True)
    audio.update(.15)
    assert audio._music[0].volume[0] == pytest.approx(.8 * .7 * 10 ** (-6 / 20))
    assert audio._music[0].sound == sound and audio._music[0].stops == stops
    audio.set_volumes(.5, .4, 1)
    director.set_options(False)
    audio.update(.15)
    assert audio._music[0].volume == pytest.approx((.2,))


def test_ending_and_postcredits_are_one_shots_then_resume_area(audio):
    director = MusicDirector(audio)
    director.request(MusicChangeRequestedEvent("ending_transform"))
    assert audio._music[audio._current].loops == 0
    director.play_postcredits("furnace_ambient")
    assert audio.track_id == "post_credits"
    audio._music[audio._current].busy = False
    audio.update(.1)
    director.update(.1)
    assert audio.track_id == "furnace_ambient"
    assert audio._music[audio._current].loops == -1


def test_generated_wav_is_seeded_stereo_16bit_and_has_no_loop_step(tmp_path):
    path, report = write_track(tmp_path, "patio_ambient", 17, duration=2, rate=8000)
    first = path.read_bytes()
    write_track(tmp_path, "patio_ambient", 17, duration=2, rate=8000)
    assert path.read_bytes() == first
    with wave.open(str(path)) as stream:
        assert (stream.getnchannels(), stream.getsampwidth(), stream.getframerate()) == (2, 2, 8000)
        data = np.frombuffer(stream.readframes(stream.getnframes()), dtype="<i2").reshape(-1, 2)
    assert len(data) == 16000 and np.array_equal(data[0], data[-1])
    assert np.max(np.abs(data.astype(np.int32))) < 32767
    assert report["integrated_lufs"] == pytest.approx(-18, abs=.1)
    assert report["sha256"] == hashlib.sha256(first).hexdigest()
    assert hashlib.sha256(data.tobytes()).hexdigest() == "6817b290012aadf4ffc2447496eea538d7d68ccd07d8070a7ad627f2e53ce2db"
    assert not np.array_equal(data, synthesize("patio_ambient", 18, duration=2, rate=8000))


@pytest.mark.parametrize("track_id", sorted(TRACKS))
def test_each_palette_and_phase_generates_finite_normalized_audio(track_id):
    pcm = synthesize(track_id, duration=1, rate=8000)
    assert pcm.shape == (8000, 2)
    assert -18.15 < integrated_lufs(pcm.astype(float) / 32768, 8000) < -17.85


def test_stereo_1khz_reference_and_absolute_silence_gate():
    t = np.arange(44100) / 44100
    tone = np.column_stack([.1 * np.sin(2 * np.pi * 1000 * t)] * 2)
    assert integrated_lufs(tone) == pytest.approx(-20, abs=.15)
    assert integrated_lufs(np.zeros_like(tone)) == float("-inf")
    assert seed_for("patio_ambient") == seed_for("patio_ambient")
    assert seed_for("patio_ambient") != seed_for("cathedral_ambient")


def test_score_durations_and_motifs_cover_requested_catalogue():
    areas = [value for key, value in TRACKS.items() if key.endswith("_ambient")]
    assert len(areas) == 5 and all(60 <= value.duration <= 120 for value in areas)
    for prefix, phases in (("boss", 2), ("tide_boss", 2), ("cinder_boss", 3)):
        scores = [TRACKS[f"{prefix}_phase{i}"] for i in range(1, phases + 1)]
        assert all(90 <= item.duration <= 180 for item in scores)
        assert all(item.motif == scores[0].motif and 4 <= len(item.motif) <= 8 for item in scores)
    assert all(not TRACKS["ending_" + key].loop for key in ("maintain", "extinguish", "transform"))


def test_cache_repairs_corruption_and_reuses_an_intact_track(tmp_path, monkeypatch):
    from dataclasses import replace
    from vigilia.engine import music_synthesis as score
    monkeypatch.setattr(score, "TRACKS", {"patio_ambient": replace(TRACKS["patio_ambient"], duration=1)})
    score.ensure_score(tmp_path)
    path = tmp_path / "patio_ambient.wav"
    original, stamp = path.read_bytes(), path.stat().st_mtime_ns
    score.ensure_score(tmp_path)
    assert path.stat().st_mtime_ns == stamp
    path.write_bytes(b"broken")
    score.ensure_score(tmp_path)
    assert path.read_bytes() == original


def test_loading_frame_does_not_advance_new_fade_before_request(audio):
    now = [10.]
    audio.music_clock = lambda: now[0]
    director = MusicDirector(audio)
    director.request(MusicChangeRequestedEvent("patio_ambient", 0))
    now[0] += 5  # area load before the next request
    director.request(MusicChangeRequestedEvent("cathedral_ambient"))
    audio.update(.25)  # clamped render delta includes preceding loading work
    assert audio._levels == [1, 0]
    now[0] += .75
    audio.update(.01)
    assert audio._levels == pytest.approx([.5, .5])
    director.request(MusicChangeRequestedEvent("boss_phase1"))
    director.update(.25)
    assert audio.track_id == ""
    now[0] += .5
    director.update(0)
    assert audio.track_id == "boss_phase1"


def test_game_routes_options_ending_and_postcredits_without_new_subscribers(audio):
    from types import SimpleNamespace
    from vigilia.game import Game
    from vigilia.core.events import AppStateChangedEvent, EventBus
    from vigilia.core.types import AppState as S
    game = Game.__new__(Game)
    game._app = SimpleNamespace(set_paused=lambda paused: None)
    game.input = SimpleNamespace(set_mode=lambda *args, **kwargs: None)
    game._clock = SimpleNamespace(reset=lambda: None)
    game.hud = game.ui_backend = None
    game.flow = SimpleNamespace(simulating=False)
    game._music_director = MusicDirector(audio)
    game._audio, game._bus = audio, EventBus()
    game._bus.subscribe(MusicChangeRequestedEvent, game._on_music)
    game.music_track = "patio_ambient"
    game._music_director.request(MusicChangeRequestedEvent("patio_ambient", 0))
    game._on_app_state_changed(AppStateChangedEvent(S.PAUSED, S.OPTIONS))
    assert audio.track_id == "patio_ambient" and audio._duck_target == pytest.approx(10 ** (-6 / 20))
    game._ending_credits = True
    game.world_state = SimpleNamespace(ending="transform", credits_seen=False)
    game._on_app_state_changed(AppStateChangedEvent(S.PAUSED, S.CREDITS))
    assert audio.track_id == "ending_transform"
    game.world_state.credits_seen, game.flow.simulating = True, True
    game.boss = None
    game._ambient_track = lambda: "furnace_ambient"
    game._on_app_state_changed(AppStateChangedEvent(S.CREDITS, S.PLAYING))
    assert audio.track_id == game.music_track == "post_credits"
