"""Generate the original UI atlas; no downloaded assets or new dependencies."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from vigilia.engine.sprite_atlas import write_atlas

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'assets/ui_atlas')
    args=parser.parse_args()
    print(json.dumps(write_atlas(args.output),indent=2))
