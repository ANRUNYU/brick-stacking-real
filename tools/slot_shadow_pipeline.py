"""Unified shadow slot pipeline: adopt expectations → export verify → consume handoff.

No arm/CAN. control_ready stays false.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tools")]

from brick_stacking.planning.placement_bridge import BundleBinding  # noqa: E402
from brick_stacking.planning.verify_handoff_consumer import consume_handoff  # noqa: E402
from brick_stacking.vision.verify_export import export_field_session  # noqa: E402


def _binding_from_bundle(bundle):
    """Build BundleBinding when clock/profile fields are complete; else None."""
    rgbd = bundle.get("rgbd") or {}
    timing = bundle.get("timing") or {}
    try:
        return BundleBinding(
            rgbd["device_id"],
            rgbd["frame_id"],
            rgbd["epoch"],
            timing["host_boot_epoch"],
            bundle["profile_hash"],
            timing["error_bound_evidence_ref"],
            2.656,
        )
    except (KeyError, TypeError, ValueError):
        return None


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("bundles", type=Path)
    p.add_argument("--request", type=Path,
                   default=ROOT / "config/planning/first_placement_review_request.adopted.json")
    p.add_argument("--phase", default="pre_grasp",
                   choices=("pre_grasp", "post_grasp", "post_place"))
    p.add_argument("--association-confirmed", action="store_true")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--now-s", type=float, default=None,
                   help="override freshness clock; default uses each row output stamp")
    args = p.parse_args(argv)

    report = export_field_session(
        args.bundles,
        phase=args.phase,
        placement_request_path=args.request,
        association_confirmed=args.association_confirmed,
    )
    req = json.loads(args.request.read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in args.bundles.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    consumption = []
    for bundle, handoff in zip(rows, report["localized_review_handoffs"]):
        timing = bundle.get("timing") or {}
        now_s = args.now_s
        if now_s is None:
            now_s = timing.get("output_monotonic_s") or timing.get("exposure_host_stamp_s")
        binding = _binding_from_bundle(bundle)
        try:
            # Incomplete binding (null clock evidence) → audit reports BUNDLE_BINDING_MISSING.
            inspection, diagnostic = consume_handoff(
                handoff, bundle, binding,
                context=None,
                now_s=float(now_s) if now_s is not None else 0.0,
                expected_color=req.get("expected_color") or "red",
            )
        except Exception as exc:  # noqa: BLE001 - shadow diagnostic path
            inspection = None
            diagnostic = {
                "status": "BLOCKED",
                "reasons": [f"CONSUMER_EXCEPTION:{type(exc).__name__}:{exc}"],
                "formal_placement_verdict": "UNKNOWN",
                "control_ready": False,
            }
        consumption.append({
            "sample_id": handoff.get("sample_id"),
            "diagnostic": diagnostic,
            "binding_present": binding is not None,
            "inspection_ready": inspection is not None,
        })

    blocked = sum(1 for c in consumption if c["diagnostic"]["status"] == "BLOCKED")
    ready = sum(1 for c in consumption if c["diagnostic"]["status"] == "SHADOW_INSPECTION_READY")
    out = {
        "schema_version": "v-slot-shadow-pipeline-0.1",
        "request": str(args.request).replace("\\", "/"),
        "request_status": req.get("status"),
        "control_ready": False,
        "motion_enabled": False,
        "export": report,
        "consumption_summary": {
            "n": len(consumption),
            "blocked": blocked,
            "shadow_inspection_ready": ready,
        },
        "consumption": consumption,
        "notes": [
            "Unified pipeline on one branch; does not wait for a separate M merge.",
            "Missing calibration_hash / association / M context keep consumer BLOCKED.",
            "Formal verify verdicts remain evidence-only; control_ready stays false.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output).replace("\\", "/"),
        "verify_verdicts": report.get("verification_verdict_counts"),
        "color_checks": report.get("color_check_counts"),
        "consumption": out["consumption_summary"],
        "control_ready": False,
    }, indent=2))


if __name__ == "__main__":
    main()
