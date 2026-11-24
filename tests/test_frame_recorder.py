"""Valida artefatos reais do cProfile com gatilhos sintéticos só no tmp_path."""

import importlib.util
import json
from pathlib import Path
import pstats
import time
from types import SimpleNamespace


spec = importlib.util.spec_from_file_location("flight_recorder", Path(__file__).parents[1] / "tools/frame_recorder.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
FrameRecorder = module.FrameRecorder


def physics():
    manifold = SimpleNamespace(get_num_manifold_points=lambda: 3)
    return SimpleNamespace(_world=SimpleNamespace(get_manifolds=lambda: [manifold]))


def payload(delay=0):
    if delay:
        time.sleep(delay)
    return sum(range(10))


def test_binary_profile_contains_exactly_thirty_preceding_frames_and_trigger(tmp_path):
    recorder = FrameRecorder(tmp_path, physics(), threshold=.01)
    for frame in range(35):
        recorder.begin(frame, False)
        payload(.025 if frame == 34 else 0)
        if frame == 34:
            recorder.collection(2, 100., 100.001)
        recorder.finish(False)
    assert not list(tmp_path.iterdir()), "I/O durante a medição"
    files = recorder.write()
    assert len(files) == 1
    combined = pstats.Stats(files[0])
    calls = sum(value[1] for key, value in combined.stats.items() if key[2] == "payload")
    assert calls == 31
    single = pstats.Stats(str(Path(files[0]).with_suffix(".frame.pstats")))
    assert sum(value[1] for key, value in single.stats.items() if key[2] == "payload") == 1
    data = json.loads(Path(files[0]).with_suffix(".json").read_text())
    assert data["previous_frames"] == 30
    assert [row["frame"] for row in data["frames"]] == list(range(4, 35))
    assert data["frames"][-1]["bullet"] == dict(manifolds=1, contacts=3)
    assert data["frames"][-1]["gc"][0]["generation"] == 2
    assert not data["frames"][-1]["minimized"]


def test_interval_gap_triggers_and_normal_run_is_named_worst(tmp_path):
    recorder = FrameRecorder(tmp_path, physics())
    assert recorder.threshold == .2
    recorder.begin(1, False)
    payload()
    recorder.finish(False)
    recorder.begin(2, False, interval=.4)  # gap injetado só para testar o hook
    recorder.discard()
    data = json.loads(Path(recorder.write()[0]).with_suffix(".json").read_text())
    assert data["frames"][-1]["trigger"] == "frame_interval"
    assert data["frames"][-1]["interval_ms"] == 400
    clean = FrameRecorder(tmp_path / "normal", physics())
    clean.begin(1, False)
    payload()
    clean.finish(False)
    assert Path(clean.write()[0]).name.startswith("worst_")


def test_retention_is_bounded_and_minimized_captures_are_identified(tmp_path):
    recorder = FrameRecorder(tmp_path, physics(), threshold=0)
    for frame in range(15):
        recorder.begin(frame, True)
        payload()
        recorder.finish(True)
    assert recorder.trigger_count == 15 and len(recorder.captures) == 8
    assert recorder.exclusions()["count"] == 15
    assert all(frames[-1][0]["minimized"] for _, frames in recorder.captures)
