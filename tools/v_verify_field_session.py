"""Export #10 verify / LocalizedReview handoff JSON from field ObservationBundle jsonl."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tools")]

from brick_stacking.vision.verify_export import export_field_session  # noqa: E402


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("bundles", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--phase", default="pre_grasp",
                   choices=("pre_grasp", "post_grasp", "post_place"))
    p.add_argument("--expected-color", required=True)
    p.add_argument("--region-id", required=True)
    p.add_argument("--target-id", default=None,
                   help="persistent target id; omit to leave association unconfirmed")
    p.add_argument("--association-confirmed", action="store_true")
    p.add_argument("--max-age-s", type=float, default=2.656)
    args = p.parse_args(argv)
    if args.association_confirmed and not args.target_id:
        p.error("--association-confirmed requires --target-id")
    report = export_field_session(
        args.bundles,
        expected_color=args.expected_color,
        region_id=args.region_id,
        target_id=args.target_id,
        phase=args.phase,
        max_age_s=args.max_age_s,
        association_confirmed=args.association_confirmed,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output).replace("\\", "/"),
        "n_frames": report["n_frames"],
        "color_check_counts": report["color_check_counts"],
        "verification_verdict_counts": report["verification_verdict_counts"],
        "control_ready": False,
    }, indent=2))


if __name__ == "__main__":
    main()
