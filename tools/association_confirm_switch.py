"""Record operator target/slot association confirmation as a durable switch JSON.

Does not mutate adopted request by default. Does not raise control_ready.
Shadow export may additionally pass --association-confirmed to slot_shadow_pipeline.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src")]

from brick_stacking.planning.pre_grasp_gates import association_switch_payload  # noqa: E402


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--request", type=Path,
                   default=ROOT / "config/planning/first_placement_review_request.adopted.json")
    p.add_argument("--operator", required=True, help="who visually confirmed the association")
    p.add_argument(
        "--evidence-ref",
        required=True,
        help="path/URI to contrast capture or annotation proving the block is the target",
    )
    p.add_argument("--notes", default="")
    p.add_argument(
        "--confirmed",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="default true; --no-confirmed writes an explicit false record",
    )
    p.add_argument("--output", type=Path, required=True)
    p.add_argument(
        "--write-adopted-overlay",
        action="store_true",
        help="also write request overlay JSON with association flag (still control_ready=false)",
    )
    p.add_argument("--overlay-output", type=Path, default=None)
    args = p.parse_args(argv)

    req = json.loads(args.request.read_text(encoding="utf-8"))
    payload = association_switch_payload(
        target_id=req["target_id"],
        reference_id=req["reference_id"],
        region_id=req["region_id"],
        slot_id=req.get("slot_id"),
        operator=args.operator,
        evidence_ref=args.evidence_ref.replace("\\", "/"),
        notes=args.notes,
        confirmed=bool(args.confirmed),
    )
    payload["source_request"] = str(args.request).replace("\\", "/")
    payload["source_request_status"] = req.get("status")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    overlay_path = None
    if args.write_adopted_overlay:
        overlay = dict(req)
        overlay["target_association_confirmed"] = bool(args.confirmed)
        overlay["association_evidence_ref"] = payload["evidence_ref"]
        overlay["association_confirm_switch"] = str(args.output).replace("\\", "/")
        overlay["control_ready"] = False
        overlay["motion_enabled"] = False
        overlay["permit"] = None
        overlay["status"] = (
            "SHADOW_ASSOCIATION_CONFIRMED_UNBOUND_CALIBRATION"
            if args.confirmed
            else req.get("status")
        )
        notes = list(overlay.get("notes") or [])
        notes.append(
            "Association overlay for shadow readiness only; calibration/clock/permit still open."
        )
        overlay["notes"] = notes
        overlay_path = args.overlay_output or args.output.with_name(
            args.output.stem + ".request_overlay.json"
        )
        overlay_path.parent.mkdir(parents=True, exist_ok=True)
        overlay_path.write_text(json.dumps(overlay, indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "output": str(args.output).replace("\\", "/"),
                "overlay": str(overlay_path).replace("\\", "/") if overlay_path else None,
                "target_association_confirmed": payload["target_association_confirmed"],
                "control_ready": False,
                "shadow_hint": (
                    "python tools/slot_shadow_pipeline.py <bundles.jsonl> "
                    "--association-confirmed --request <overlay-or-adopted> --output <shadow.json>"
                ),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
