"""Check wrist-path-0.1 against wrist-target-0.1 before live auth (issue #31)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from brick_stacking.wrist_handoff.wrist_path_check import check_wrist_path
from brick_stacking.wrist_handoff.wrist_target import file_sha256


def main() -> None:
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("wrist_target", type=Path)
    p.add_argument("wrist_path", type=Path)
    p.add_argument("--tip-poses", type=Path, default=None, help="optional FK tips by segment end name")
    p.add_argument("--output", type=Path, default=None)
    args = p.parse_args()

    target = json.loads(args.wrist_target.read_text(encoding="utf-8-sig"))
    path = json.loads(args.wrist_path.read_text(encoding="utf-8-sig"))
    tips = None
    if args.tip_poses is not None:
        tips = json.loads(args.tip_poses.read_text(encoding="utf-8-sig"))
    report = check_wrist_path(
        wrist_target=target,
        wrist_path=path,
        request_sha256=file_sha256(args.wrist_target),
        tip_poses_by_segment_end=tips,
    )
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    raise SystemExit(0 if report["ok"] else 2)


if __name__ == "__main__":
    main()
