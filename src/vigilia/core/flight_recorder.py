"""Flight recorder de diagnóstico. I/O e merge dos perfis só após a medição.

Os arquivos .pstats são perfis binários CPython/cProfile, legíveis por pstats;
não são gravações do servidor gráfico Panda PStats (1.10 não exporta via cliente).
"""

from collections import deque
from datetime import datetime, timezone
import cProfile
import json
import pstats
import time


class FrameRecorder:
    def __init__(self, directory, sample_contacts, *, threshold=.2, previous=30, on_capture=None):
        self.directory = directory
        self.sample_contacts, self.on_capture = sample_contacts, on_capture
        self.threshold = threshold
        self.ring = deque(maxlen=previous + 1)
        self.current = None
        self.captures = []
        self.worst = None
        self.trigger_count = 0
        self.excluded_count = 0
        self.excluded_seconds = 0.0

    def begin(self, frame, minimized, interval=None):
        if interval is not None and self.ring:
            row = self.ring[-1][0]
            row["interval_ms"] = interval * 1000
            row["minimized"] = bool(row["minimized"] or minimized)
            if interval >= self.threshold and row["wall_ms"] < self.threshold * 1000:
                row["trigger"] = "frame_interval"
                self._capture()
        self.current = dict(frame=frame, minimized=minimized, start=time.perf_counter(),
                            cpu_start=time.thread_time(), stages={}, slow_calls=[], gc=[])
        self.profile = cProfile.Profile()
        self.profile.enable()

    def stage(self, label, start, cpu_start):
        if self.current is None:
            return
        elapsed = time.perf_counter() - start
        cpu = time.thread_time() - cpu_start
        row = self.current["stages"].setdefault(label, dict(calls=0, wall_ms=0., cpu_ms=0., max_ms=0.))
        row["calls"] += 1
        row["wall_ms"] += elapsed * 1000
        row["cpu_ms"] += cpu * 1000
        row["max_ms"] = max(row["max_ms"], elapsed * 1000)
        if elapsed >= .001:
            self.current["slow_calls"].append(dict(label=label, start=start, wall_ms=elapsed*1000, cpu_ms=cpu*1000))

    def collection(self, generation, start, end):
        if self.current is not None:
            self.current["gc"].append(dict(generation=generation, start=start, end=end, ms=(end-start)*1000))

    def finish(self, minimized):
        if self.current is None:
            return
        self.profile.disable()
        row, self.current = self.current, None
        row["end"] = time.perf_counter()
        row["wall_ms"] = (row["end"] - row["start"]) * 1000
        row["cpu_ms"] = (time.thread_time() - row.pop("cpu_start")) * 1000
        row["minimized"] = bool(minimized or row["minimized"])
        # Bullet 1.10.16: contatos são a soma dos pontos de cada manifold.
        row["bullet"] = self.sample_contacts()
        self.ring.append((row, self.profile))
        self.profile = None
        if self.worst is None or row["wall_ms"] > self.worst[-1][0]["wall_ms"]:
            self.worst = tuple(self.ring)
        if row["minimized"]:
            self.excluded_count += 1
            self.excluded_seconds += row["wall_ms"] / 1000
        if row["wall_ms"] >= self.threshold * 1000:
            # Capturar também minimização, mas sem classificá-la como pico de combate.
            row["trigger"] = "frame_body"
            self._capture()

    def _capture(self):
        self.trigger_count += 1
        capture = (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ"), tuple(self.ring))
        self.captures.append(capture)
        # Memória limitada: oito piores, priorizando janelas não minimizadas.
        self.captures.sort(key=lambda entry: (not entry[1][-1][0]["minimized"],
            max(entry[1][-1][0]["wall_ms"], entry[1][-1][0].get("interval_ms", 0))), reverse=True)
        del self.captures[8:]
        if self.on_capture:
            self.on_capture(*capture)

    def discard(self):
        if self.current is not None:
            self.profile.disable()
            self.current = None

    def write(self):
        self.discard()
        files = []
        captures = [(f"spike_{timestamp}", frames) for timestamp, frames in self.captures]
        if self.worst and not self.captures:
            captures.append((f"worst_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')}", self.worst))
        return [self.write_capture(name, frames) for name, frames in captures]

    def write_capture(self, name, frames):
        self.directory.mkdir(parents=True, exist_ok=True)
        stem = self.directory / name
        profiles = [profile for _, profile in frames]
        target = stem.with_suffix(".pstats")
        temporary = stem.with_suffix(".pstats.tmp")
        pstats.Stats(*profiles).dump_stats(str(temporary))
        temporary.replace(target)
        temporary = stem.with_suffix(".frame.pstats.tmp")
        profiles[-1].dump_stats(str(temporary))
        temporary.replace(stem.with_suffix(".frame.pstats"))
        report = dict(format="CPython cProfile/pstats binary (not Panda server recording)",
                      exceeded_threshold=name.startswith("spike_"), trigger_ms=self.threshold*1000,
                      previous_frames=len(frames)-1, total_triggered=self.trigger_count,
                      retained_captures=len(self.captures), capture_limit=8,
                      frames=[row for row, _ in frames])
        temporary = stem.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
        temporary.replace(stem.with_suffix(".json"))
        return str(target)

    def exclusions(self):
        return dict(count=self.excluded_count, total_ms=round(self.excluded_seconds*1000, 3), reason="window_minimized")
