"""Observação de QA: perfis fora da thread do jogo e quarentena por build."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import gc
import hashlib
import json
from pathlib import Path
import threading
import time
import zipfile
import platform
import sys
from importlib.metadata import version

from vigilia.core.flight_recorder import FrameRecorder


def build_fingerprint(root):
    digest = hashlib.sha256()
    paths = [root / "main.py"] + [root / name for name in ("requirements.txt", "pyproject.toml") if (root / name).exists()]
    for directory in ("src", "data", "assets"):
        paths += [p for p in (root / directory).rglob("*") if p.is_file() and
                  "__pycache__" not in p.parts and p.suffix != ".pyc" and p.name != "settings.toml"]
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def archive_build(root, build_id):
    directory = root / "artifacts/qa" / build_id
    archive = directory / "source.zip"
    if archive.exists():
        return
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / "source.zip.tmp"
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for path in [root / "main.py", *[root / name for name in ("requirements.txt", "pyproject.toml") if (root / name).exists()], *[p for d in ("src", "data", "assets") for p in (root / d).rglob("*")
                if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc" and p.name != "settings.toml"]]:
            output.write(path, path.relative_to(root))
    temporary.replace(archive)
    (directory / "manifest.json").write_text(json.dumps(dict(build_id=build_id,
        archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(), python=sys.version,
        platform=platform.platform(), dependencies={name: version(name) for name in ("panda3d", "pygame", "numpy")}), indent=2), encoding="utf8")


class QADiagnostics:
    def __init__(self, app, directory, sample_contacts, context, *, build_id, report_path, registry_path=None):
        self.app, self.context = app, context
        self.build_id, self.report_path = build_id, Path(report_path)
        self.registry_path = Path(registry_path) if registry_path else self.report_path.with_name("quarantine.json")
        self.main_thread = threading.get_ident()
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="qa-profile-writer")
        self.spikes, self.errors, self.futures, self.originals = [], [], [], []
        self.quarantined, self.closed = False, False
        self.triaged_profiles = {}
        if self.registry_path.exists():
            previous = json.loads(self.registry_path.read_text(encoding="utf8"))
            if previous.get("build_id") == build_id:
                self.spikes = previous.get("spikes", [])
                self.triaged_profiles = previous.get("triaged_profiles", {})
                self.quarantined = any(path not in self.triaged_profiles for path in self.spikes)
        self.session_spikes = []
        self.recorder = FrameRecorder(Path(directory), sample_contacts, on_capture=self._capture)
        self.previous = None
        self.gc_started = {}
        gc.callbacks.append(self._gc)
        app.taskMgr.add(self.begin, "qa-frame-start", sort=9)
        app.taskMgr.add(self.finish, "qa-frame-end", sort=51)

    def wrap(self, owner, name, label):
        original = getattr(owner, name)
        def measured(*args, **kwargs):
            start, cpu = time.perf_counter(), time.thread_time()
            try:
                return original(*args, **kwargs)
            finally:
                if threading.get_ident() == self.main_thread:
                    self.recorder.stage(label, start, cpu)
        self.originals.append((owner, name, original))
        setattr(owner, name, measured)

    def begin(self, task):
        now = time.perf_counter()
        interval = None if self.previous is None else now - self.previous
        self.previous = now
        self.recorder.begin(self.app._clock.get_frame_count(), bool(self.app.mainWinMinimized), interval)
        self.recorder.current["context"] = self.context()
        return task.cont

    def finish(self, task):
        self.recorder.finish(bool(self.app.mainWinMinimized))
        return task.cont

    def _gc(self, phase, info):
        generation = info["generation"]
        if phase == "start":
            self.gc_started[generation] = time.perf_counter()
        elif generation in self.gc_started:
            self.recorder.collection(generation, self.gc_started.pop(generation), time.perf_counter())

    def _capture(self, timestamp, frames):
        self.quarantined = True
        path = self.recorder.directory / f"spike_{timestamp}.pstats"
        self.spikes.append(str(path))
        self.session_spikes.append(str(path))
        frozen = tuple((deepcopy(row), profile) for row, profile in frames)
        self.futures = [future for future in self.futures if not future.done() or future.exception()]
        if len(self.futures) >= 8:
            self.errors.append("capture_writer_backlog: build quarantined; capture not persisted")
            return
        report = self.report()
        def persist():
            self.recorder.write_capture(f"spike_{timestamp}", frozen)
            self._write_report(report)
        self.futures.append(self.worker.submit(persist))

    def report(self):
        return dict(build_id=self.build_id, diagnostics=True, format="CPython cProfile/pstats binary",
            quarantined=self.quarantined, spikes=list(self.spikes), capture_errors=list(self.errors),
            session_spikes=list(self.session_spikes), triaged_profiles=dict(self.triaged_profiles),
            trigger_count=self.recorder.trigger_count, dropped_captures=len(self.errors),
            excluded_samples=self.recorder.exclusions(),
            gate="Any >200ms QA spike quarantines this build until evidence is triaged; shared spikes do not establish engine/driver causality.")

    def _write_report(self, report):
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.report_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(report, indent=2), encoding="utf8")
        temporary.replace(self.report_path)
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.registry_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(report, indent=2), encoding="utf8")
        temporary.replace(self.registry_path)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.recorder.discard()
        self.app.taskMgr.remove("qa-frame-start")
        self.app.taskMgr.remove("qa-frame-end")
        gc.callbacks.remove(self._gc)
        for owner, name, original in reversed(self.originals):
            setattr(owner, name, original)
        self.worker.shutdown(wait=True)
        for future in self.futures:
            try:
                future.result()
            except Exception as error:
                self.errors.append(f"capture_write_failed: {error}")
        if not self.recorder.trigger_count:
            self.recorder.write()
        self._write_report(self.report())
