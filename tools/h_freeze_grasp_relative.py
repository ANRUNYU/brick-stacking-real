"""Freeze grasp-relative-0.1 from Line H teach samples (issue #28)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from brick_stacking.wrist_handoff.freeze_from_teach import freeze_grasp_relative_from_teach


def main() -> None:
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("teach_bundle", type=Path, help="JSON with samples[] teach records")
    p.add_argument("output", type=Path)
    p.add_argument("--relative-version", required=True)
    p.add_argument("--pack-version", required=True)
    args = p.parse_args()
    data = json.loads(args.teach_bundle.read_text(encoding="utf-8-sig"))
    samples = data["samples"] if isinstance(data, dict) and "samples" in data else data
    out = freeze_grasp_relative_from_teach(
        relative_version=args.relative_version,
        pack_version=args.pack_version,
        samples=samples,
        notes=tuple(data.get("notes") or []) if isinstance(data, dict) else (),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
