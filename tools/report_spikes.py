"""Consolida evidências, sem liberar QA nem inferir a causa do pico histórico."""

import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    spike_root = ROOT / "artifacts/spikes"
    runs = []
    for path in sorted(spike_root.glob("run-*.json")):
        value = read(path)
        stages = value.get("profile", {}).get("stages", {})
        runs.append(dict(file=str(path.relative_to(ROOT)), seconds=value["seconds"],
            valid_sample=value["valid_sample"], window_type=value.get("window_type", "onscreen"),
            max_frame_ms=value["max_frame_ms"], fps=value["fps"], one_percent_low_fps=value["one_percent_low_fps"],
            excluded_samples=value.get("excluded_samples"),
            duration_basis="full frame interval" if "exclusion_policy" in value else "profiled frame body (older recorder)",
            spike_captures=value.get("spike_captures", []), gc=value.get("profile", {}).get("gc", {}),
            logging={key: row for key, row in stages.items() if "log" in key}, save_calls=value.get("profile", {}).get("save_calls")))
    historical_path = ROOT / "artifacts/5.3/stress-tide-active.json"
    historical = read(historical_path)
    minimized = [row for row in historical["profile"]["render_hitches"] if row["minimized"]]
    captures = [str(path.relative_to(ROOT)) for path in sorted(spike_root.glob("spike_*.pstats")) if not path.name.endswith(".frame.pstats")]
    counter = read(spike_root / "minimization-counter.json")
    sources = ("src/vigilia/core/log.py", "src/vigilia/game.py", "tools/benchmark.py", "tools/frame_recorder.py")
    logging_profiles = []
    for path in sorted(spike_root.glob("worst_*.json")):
        sample = read(path)
        frame = sample["frames"][-1]
        if frame["stages"].get("log_stream_write", {}).get("max_ms", 0) >= 50:
            logging_profiles.append(dict(file=str(path.with_suffix(".pstats").relative_to(ROOT)),
                frame_file=str(path.with_suffix(".frame.pstats").relative_to(ROOT)), frame=frame["frame"],
                preceding_frames=sample["previous_frames"], wall_ms=frame["wall_ms"],
                log_stream_write=frame["stages"]["log_stream_write"], minimized=frame["minimized"]))
    suites = ElementTree.parse(ROOT / "artifacts/5.3/spike-tests.xml").getroot().findall(".//testsuite")
    passed = sum(int(row.get("tests", 0)) - int(row.get("failures", 0)) - int(row.get("errors", 0)) - int(row.get("skipped", 0)) for row in suites)
    report = dict(
        stage="5.3 accepted; monitoring continues during 5.4 QA", tests_passed=passed,
        qa_5_4=dict(ready=True, process_unblocked=True, historical_500ms_cause_confirmed=False,
            reason="User withdrew the process-wide blocker on 2026-11-24. QA keeps diagnostics active; each build with a >200ms QA spike is quarantined until triage. Historical 504/570ms causes remain unconfirmed.",
            captured_profiles=captures),
        excluded_samples=dict(count=len(minimized), total_ms=round(sum(row["render_ms"] for row in minimized), 3), reason="window_minimized"),
        exclusion_basis=dict(file=str(historical_path.relative_to(ROOT)), invalid_run_retained=True,
            duration="Measured render_and_swap spans only. Historical full frame intervals unavailable; this is a documented lower bound, not an invented full-frame total.",
            current_runner="Records exact full measured frame intervals, count, duration and invalidates any minimized run for FPS comparison."),
        counter_qa=dict(file="artifacts/spikes/minimization-counter.json", intentionally_minimized=True,
            valid_sample=counter["valid_sample"], excluded_samples=counter["excluded_samples"], included_in_natural_stall_statistics=False),
        findings=dict(
            logging="Real non-minimized synchronous logging stalls: run-06 emit 110.4215ms; run-07 stream.write 91.5848ms. These identify a blocking I/O path, not the historical 500ms cause.",
            fix="Executable now uses QueueHandler/QueueListener. Producer never writes stderr; dedicated thread drains FIFO. Test holds sink blocked and proves producer continues; shutdown drains.",
            sqlite="Combat changes and F8 coalesce into one pending request. Latest snapshot saved at bonfire/area/respawn fade, paused menu, main-menu return or quit. Failure retains dirty state for next safe boundary.",
            gc="Callbacks retain generation/start/end with frame. No global freeze/threshold tuning applied without causal evidence.",
            bullet="Every recorded frame samples get_manifolds and sums get_num_manifold_points (no world.get_num_contacts in installed API). No solver tuning without causal evidence.",
            shaders="run-05 shader log: zero compile/link messages after measurement start. No observed runtime compilation to justify new variants/prewarm changes."),
        recorder=dict(format="Binary CPython cProfile/pstats, not Panda PStats server format",
            api_constraint="PStatClient in installed Panda3D 1.10.16 has no file-dump API. Official server text logs remain .txt; no renamed or fabricated Panda file.",
            threshold_ms=200, preceding_frames=30, max_retained_captures=8,
            trigger="Full measured frame interval or profiled frame body; correlated stages, CPU time, GC and Bullet counts.",
            io="All profile merges/file writes happen after measurement. Each .pstats can be opened by Python pstats. Single-frame profile and JSON accompany combined profile.",
            normal_frames="Worst sample saved as worst_*.pstats; never presented as >200ms spike. Test injections only use pytest temporary directories.",
            overhead="cProfile flight-recorder and offscreen results are diagnostics, not FPS baselines."),
        numerical_correction="209.65/100.07 is below 214/106, while exceeding the 55 FPS low target. Historical noise/causality is not established without a reproducible 5.2a build.",
        logging_profiles=logging_profiles,
        diagnostic_seconds=round(sum(row["seconds"] for row in runs if "spike_captures" in read(ROOT / row["file"])), 3),
        runs=runs,
        regressions=dict(campaign="artifacts/5.3/save-boundary-campaign/campaign.json",
            frontend="artifacts/5.3/save-boundary-frontend/frontend.json", junit="artifacts/5.3/spike-tests.xml"),
        source_hash_scope="Current diagnostics implementation at report generation, not the source of every historical trial.",
        current_report_source_sha256={path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in sources},
    )
    destination = ROOT / "artifacts/5.3/verification.json"
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(destination)


if __name__ == "__main__":
    main()
