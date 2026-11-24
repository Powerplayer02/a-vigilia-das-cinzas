"""Reproduz o código arquivado, trocando somente a instrumentação do benchmark."""

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "artifacts/5.3/diagnostics/source-5.2b.zip")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", default=10, type=float)
    parser.add_argument("--window-type", choices=("onscreen", "offscreen"), default="onscreen")
    parser.add_argument("--spike-directory", type=Path)
    parser.add_argument("--pstats-port", type=int)
    parser.add_argument("--shadow-quality", choices=("off", "low", "medium", "high"), default="medium")
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vigilia-immutable-benchmark-") as directory:
        frozen = Path(directory)
        with zipfile.ZipFile(args.source) as archive:
            archive.extractall(frozen)
        shutil.copyfile(ROOT / "tools/benchmark.py", frozen / "tools/benchmark.py")
        shutil.copyfile(ROOT / "tools/frame_recorder.py", frozen / "tools/frame_recorder.py")
        shutil.copyfile(ROOT / "src/vigilia/core/flight_recorder.py", frozen / "src/vigilia/core/flight_recorder.py")
        with output.with_suffix(".log").open("w") as log:
            recorder = ["--spike-directory", str(args.spike_directory.resolve())] if args.spike_directory else []
            stats = ["--pstats-port", str(args.pstats_port)] if args.pstats_port else []
            result = subprocess.run([sys.executable, str(frozen / "tools/benchmark.py"), "--seconds", str(args.seconds),
                "--particles", "500", "--profile", "--shadow-quality", args.shadow_quality,
                "--window-type", args.window_type,
                "--output", str(output), *recorder, *stats], stdout=log, stderr=log)
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
