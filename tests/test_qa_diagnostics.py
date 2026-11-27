"""Injeções identificadas no tmp_path validam captura e isolamento por build."""

import json
import pstats
import time
from types import SimpleNamespace

from vigilia.engine.diagnostics import QADiagnostics, build_fingerprint


class Tasks:
    def add(self, *args, **kwargs):
        pass
    def remove(self, name):
        pass


def monitor(tmp_path, build):
    app = SimpleNamespace(taskMgr=Tasks(), mainWinMinimized=False,
        _clock=SimpleNamespace(get_frame_count=lambda: 1))
    return QADiagnostics(app, tmp_path / "spikes", lambda: dict(manifolds=2, contacts=3),
        lambda: dict(area="test-only-injection"), build_id=build, report_path=tmp_path / build / "diagnostics.json")


def test_capture_reaches_disk_before_session_closes_and_quarantines_only_its_build(tmp_path):
    slow = monitor(tmp_path, "synthetic-A")
    slow.recorder.threshold = .01
    task = SimpleNamespace(cont="continue")
    try:
        for _ in range(35):
            slow.begin(task)
            slow.finish(task)
        slow.begin(task)
        time.sleep(.025)
        slow.finish(task)
        for future in slow.futures:
            future.result(timeout=10)
        assert slow.quarantined and slow.spikes
        profile = pstats.Stats(slow.spikes[-1])
        assert profile.total_tt >= .02
        report = json.loads(slow.report_path.read_text())
        assert report["quarantined"] and report["dropped_captures"] == 0
        clip = json.loads(slow.recorder.directory.joinpath(slow.spikes[-1]).with_suffix(".json").read_text())
        assert clip["previous_frames"] == 30
    finally:
        slow.close()
    retry = monitor(tmp_path, "synthetic-A")
    try:
        assert retry.quarantined  # outra sessão da mesma build não apaga o gate
    finally:
        retry.close()
    normal = monitor(tmp_path, "synthetic-B")
    try:
        normal.begin(task)
        normal.finish(task)
        assert not normal.quarantined
    finally:
        normal.close()
    assert not json.loads(normal.report_path.read_text())["quarantined"]


def test_fingerprint_changes_with_code_and_ignores_local_options(tmp_path):
    (tmp_path / "main.py").write_text("version=1")
    for folder in ("src", "data", "assets"):
        (tmp_path / folder).mkdir()
    before = build_fingerprint(tmp_path)
    (tmp_path / "data/settings.toml").write_text("local=true")
    assert build_fingerprint(tmp_path) == before
    (tmp_path / "main.py").write_text("version=2")
    assert build_fingerprint(tmp_path) != before


def test_native_render_stage_retains_resource_counts_on_both_sides(tmp_path):
    sample = monitor(tmp_path, "native-counters-test")
    task = SimpleNamespace(cont="continue")
    count = [2]
    sample.prepared = SimpleNamespace(get_num_prepared_textures=lambda: count[0],
        get_num_queued_shaders=lambda: 0)
    try:
        sample.begin(task)
        sample.before_render(task)
        count[0] = 3
        sample.finish(task)
        row = sample.recorder.ring[-1][0]
        assert row["native_resources_before"]["prepared_textures"] == 2
        assert row["native_resources_after"]["prepared_textures"] == 3
        assert row["native_resources_after"]["queued_shaders"] == 0
        assert row["stages"]["native_render_and_swap"]["calls"] == 1
    finally:
        sample.close()


def test_interaction_key_is_a_format_value_not_catalog_lookup_argument():
    from pathlib import Path
    from vigilia.core.locale import Localizer
    localizer = Localizer(Path(__file__).parents[1] / "data/locale")
    assert localizer.t("ending.interact", key="F").startswith("F ")
    assert "F" in localizer.t("context.passage", key="F", name="Destino")
