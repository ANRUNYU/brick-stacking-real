"""Hardware-free CLI for reviewing the draft contract and interface examples."""

import argparse
import json
from collections.abc import Sequence

from . import SCHEMA_VERSION, SceneSnapshot


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Print a draft M0 interface example offline.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--dry-run", action="store_true", required=True, help="Print JSON only."
    )
    parser.parse_args(argv)

    scene: SceneSnapshot = {
        "scene_version": "dry-run-0",
        "blocks_by_id": {},
        "slots_by_id": {},
    }
    print(json.dumps({
        "schema_version": SCHEMA_VERSION,
        "mode": "dry-run",
        "motion_enabled": False,
        "scene": scene,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
