"""Gera a trilha original sem abrir janela ou dispositivo de áudio."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vigilia.engine.music_synthesis import TRACKS, write_track, ensure_score


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--track", choices=sorted(TRACKS))
    parser.add_argument("--seed", type=int)
    parser.add_argument("--output", type=Path, default=ROOT / "assets/music")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    if args.all:
        if args.track or args.seed is not None:
            parser.error("--all usa as seeds canônicas; não combine com --track/--seed")
        ensure_score(args.output)
        print(json.dumps(dict(directory=str(args.output.resolve()), tracks=len(TRACKS))))
    elif args.track:
        path, report = write_track(args.output, args.track, args.seed)
        print(json.dumps(dict(path=str(path.resolve()), **report), indent=2))
    else:
        parser.error("Informe --track <id> ou --all")


if __name__ == "__main__":
    main()
