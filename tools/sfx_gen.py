"""Export original, seeded 44.1 kHz stereo PCM effects without opening a device."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from vigilia.engine.sfx_synthesis import SPECS, ensure_sfx, write_sfx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clip", choices=sorted(SPECS))
    parser.add_argument("--seed", type=int)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "assets/sfx")
    args = parser.parse_args()
    if args.all and not args.clip and args.seed is None:
        ensure_sfx(args.output)
        print(json.dumps(dict(clips=len(SPECS), output=str(args.output.resolve()))))
    elif args.clip and not args.all:
        path, metadata = write_sfx(args.output, args.clip, args.seed)
        print(json.dumps(dict(path=str(path.resolve()), **metadata), indent=2))
    else:
        parser.error("Use --clip <id> [--seed <int>] or --all")


if __name__ == "__main__":
    main()
