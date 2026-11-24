"""Consolida evidência local da 5.4 e mantém observações não confirmadas."""

import json
from pathlib import Path
import sys
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from vigilia.engine.diagnostics import build_fingerprint


def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf8"))


def main():
    build_id = build_fingerprint(ROOT)
    native = read("artifacts/5.4/native/campaign.json")
    assert native["build_id"] == build_id and not native["quarantined"]
    registry = read(f"artifacts/qa/{build_id}/quarantine.json")
    assert not registry["quarantined"] and not registry["capture_errors"]
    old = {(r.get("classname"), r.get("name")) for r in ElementTree.parse(ROOT / "artifacts/5.3/spike-tests.xml").iter("testcase")}
    tests = ElementTree.parse(ROOT / "artifacts/5.4/tests.xml")
    names = {(r.get("classname"), r.get("name")) for r in tests.iter("testcase")}
    assert not old - names
    suites = tests.getroot().findall(".//testsuite")
    assert not any(int(s.get("failures", 0)) or int(s.get("errors", 0)) for s in suites)
    baseline = read("artifacts/5.4/stress-final-certified.json")
    assert baseline["source_build_id"] == build_id and baseline["valid_sample"]
    assert baseline["live_enemy_bodies"] == 21 and baseline["particles_min_max"] == [500, 500]
    assert baseline["one_percent_low_fps"] >= 55
    stress_qa = []
    for name in ("offscreen", "window"):
        report = read(f"artifacts/5.4/stress-qa-{name}.diagnostics.json")
        assert report["build_id"] == build_id
        assert all(path in registry.get("triaged_profiles", {}) for path in report["spikes"])
        assert not report["capture_errors"]
        stress_qa.append(dict(file=f"artifacts/5.4/stress-qa-{name}.json", diagnostics=report))
    invalid = read("artifacts/5.4/stress-final-build.json")
    outlier = max(invalid["profile"]["render_hitches"], key=lambda r: r["render_ms"])
    report = dict(date="2026-11-24", stage="5.4", status="Local functional QA passed; not a remote/hardware/full-manual certification",
        build_id=build_id, build_manifest=f"artifacts/qa/{build_id}/manifest.json",
        source_archive=f"artifacts/qa/{build_id}/source.zip", qa_quarantine_registry=registry,
        quit_save_triage=read("artifacts/5.4/quit-save-triage.json"),
        earlier_same_build_summary=read("artifacts/5.4/history/stress-final-95332696e0a37cbd-summary-before-path-isolation.json"),
        tests=dict(passed=sum(int(s.get("tests",0)) for s in suites), additional=len(names-old),
            previous_regressions_preserved=True, junit="artifacts/5.4/tests.xml"),
        content=dict(areas=["ruinas_subterraneas", "forno_da_vigilia"],
            boss="Custódio da Última Chama", hp=5600, poise=200, souls_base=6000, phases=[1,2,3], thresholds=[.66,.33],
            environmental_hazard="Two alternating 2.4m fire vents; 90-step telegraph, pulses at 90/110/130; resistance and current iframes apply; saved clock",
            endings=["maintain", "extinguish", "transform"], ending_immutable=True, post_credits_persisted=True,
            menus="Existing five-class creation/main/pause/slots/options retained", map="Discovered-region overview and selectable focus via IMapDataProvider"),
        native_qa=native, instrumented_load_tests=stress_qa,
        launcher=dict(qa=read("artifacts/5.4/launcher-qa.json"), release=read("artifacts/5.4/launcher-release.json")),
        performance=dict(file="artifacts/5.4/stress-final-certified.json", source_build_id=baseline["source_build_id"],
            renderer=baseline["renderer"], resolution=baseline["resolution"], seconds=baseline["seconds"], vsync=baseline["vsync"],
            fps=baseline["fps"], one_percent_low_fps=baseline["one_percent_low_fps"], max_frame_ms=baseline["max_frame_ms"],
            ai_tick_mean_ms=baseline["ai_tick_mean_ms"], a_star_isolated=baseline["path_isolated"],
            save_calls=baseline["profile"]["save_calls"], excluded_samples=baseline["excluded_samples"]),
        invalid_performance_sample=dict(source_build_id=invalid.get("source_build_id"), file="artifacts/5.4/stress-final-build.json", excluded_from_baseline=True,
            excluded_samples=invalid["excluded_samples"], separate_render_outlier=outlier,
            note="312.977ms render span had minimized=False; cause unconfirmed. Same run also had 23 minimized intervals. Do not attribute this outlier to minimization. Release timing run had no cProfile binary recorder. Full QA recorder load repeats did not reproduce it."),
        screenshot_triage=read("artifacts/5.4/screenshot-triage.json"),
        logging_findings=[
            "75-110ms synchronous stderr writes observed in older code; dedicated queue/consumer removes this I/O path from gameplay.",
            "No evidence of queue-full loss; SimpleQueue has no configured capacity or programmed discard. Unit test blocks sink, proves producer continues and shutdown drains FIFO.",
            "Current QA recorder: zero capture write errors/dropped captures; writer overload/error is reported and quarantines the build.",
            "cProfile adds overhead; main.py --no-diagnostics avoids constructing it. INFO terminal verbosity remains cosmetic.",
            "QA screenshot PNG encoding caused five real >200ms captures in rejected build 3e81ed59cce24a54; all analyzed. Encoding now occurs after measurement."],
        historical_stall=dict(status="Not confirmed fixed", observations="380.217s prior mixed diagnostic trials without matching combat recurrence; includes archived and current code, not a per-session frequency estimate.",
            logging_save_causality="Blocking I/O paths were removed; no proof they caused the historical 504/570ms combat stalls.",
            policy="User withdrew process-wide blocker on 2026-11-24. QA instrumentation stays active; an observed >200ms QA spike quarantines only that build until documented triage. Shared spikes do not establish engine/driver cause."),
        limitations=["QA used disclosed HP/victory/teleport seeds; not a manual complete playthrough or balance certification.",
            "Native frontend/campaign/regressions validated locally; remote CI not executed, no repository remote available.",
            "Physical gamepad not available; existing simulated input tests retained.",
            "Authentic historical v1/v2 save captures remain unavailable; no synthetic files relabeled as authentic.",
            "Measurements on GTX1660Ti only; other GPU/platform certification remains pending."],
        regressions=dict(campaign="artifacts/5.4/regressions/campaign/campaign.json", classes="artifacts/5.4/regressions/classes/classes.json"),
        next_stage="5.5: optional minibosses and lore; 5.6: map expansion and polish")
    destination = ROOT / "artifacts/5.4/verification.json"
    destination.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf8")
    print(json.dumps(dict(build_id=build_id, tests=report["tests"], fps=baseline["fps"], low=baseline["one_percent_low_fps"], quarantined=False)))


if __name__ == "__main__":
    main()
