"""Unified shadow slot pipeline: adopt expectations → export verify → consume handoff.

No arm/CAN. control_ready stays false.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tools")]

from brick_stacking.localization.calibration_binding import (  # noqa: E402
    apply_binding_to_bundle,
    load_binding,
)
from brick_stacking.planning.placement_bridge import BundleBinding  # noqa: E402
from brick_stacking.planning.placement_review import Context  # noqa: E402
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


def _repo_rel(path: Path) -> str:
    text = str(path.resolve()).replace("\\", "/")
    root = str(ROOT.resolve()).replace("\\", "/")
    if text.startswith(root + "/"):
        return text[len(root) + 1 :]
    return text


def _load_rows(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _stamp_rows(rows: list[dict], calibration_binding: dict | None) -> list[dict]:
    if calibration_binding is None:
        return rows
    return [apply_binding_to_bundle(row, calibration_binding) for row in rows]


def _write_temp_jsonl(rows: list[dict]) -> Path:
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".jsonl", delete=False
    )
    with handle as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return Path(handle.name)


def _build_m_context(req: dict, bundle: dict) -> Context:
    """Minimal legal Context from request + stamped bundle fields. No invented hashes."""
    rgbd = bundle.get("rgbd") or {}
    timing = bundle.get("timing") or {}
    formal = req.get("formal_verify_reference") or {}
    scene_version = (
        req.get("scene_version")
        or formal.get("geometry_version")
        or req.get("reference_id")
    )
    calibration_hash = bundle.get("calibration_hash") or req.get("calibration_hash")
    profile_hash = bundle.get("profile_hash") or req.get("profile_hash")
    epoch = rgbd.get("epoch") or req.get("epoch")
    clock_domain = timing.get("host_clock_domain")
    frame_id = rgbd.get("frame_id") or req.get("camera_frame")
    missing = [
        name
        for name, value in (
            ("target_id", req.get("target_id")),
            ("frame_id", frame_id),
            ("scene_version", scene_version),
            ("calibration_hash", calibration_hash),
            ("profile_hash", profile_hash),
            ("epoch", epoch),
            ("clock_domain", clock_domain),
        )
        if not value
    ]
    if missing:
        raise ValueError(f"cannot build M Context; missing fields: {','.join(missing)}")
    return Context(
        req["target_id"],
        "block",
        frame_id,
        scene_version,
        calibration_hash,
        profile_hash,
        epoch,
        clock_domain,
    )


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("bundles", type=Path)
    p.add_argument("--request", type=Path,
                   default=ROOT / "config/planning/first_placement_review_request.adopted.json")
    p.add_argument("--phase", default="pre_grasp",
                   choices=("pre_grasp", "post_grasp", "post_place"))
    p.add_argument("--association-confirmed", action="store_true")
    p.add_argument(
        "--calibration-binding",
        type=Path,
        default=None,
        help="ACTIVE current-binding JSON; stamps calibration_hash onto bundles for shadow only",
    )
    p.add_argument(
        "--build-m-context",
        action="store_true",
        help="construct minimal legal Context from request+bundle for shadow Inspection only",
    )
    p.add_argument(
        "--stamped-bundles-output",
        type=Path,
        default=None,
        help="optional durable jsonl of calibration-stamped bundles",
    )
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--now-s", type=float, default=None,
                   help="override freshness clock; default uses each row output stamp")
    args = p.parse_args(argv)

    req = json.loads(args.request.read_text(encoding="utf-8"))
    calibration_binding = load_binding(args.calibration_binding) if args.calibration_binding else None
    rows = _stamp_rows(_load_rows(args.bundles), calibration_binding)
    if args.stamped_bundles_output is not None:
        args.stamped_bundles_output.parent.mkdir(parents=True, exist_ok=True)
        args.stamped_bundles_output.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )
    export_path = args.stamped_bundles_output
    temp_path = None
    if export_path is None:
        temp_path = _write_temp_jsonl(rows)
        export_path = temp_path
    try:
        report = export_field_session(
            export_path,
            phase=args.phase,
            placement_request_path=args.request,
            association_confirmed=args.association_confirmed,
        )
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

    consumption = []
    context_notes = []
    for bundle, handoff in zip(rows, report["localized_review_handoffs"]):
        timing = bundle.get("timing") or {}
        now_s = args.now_s
        if now_s is None:
            now_s = timing.get("output_monotonic_s") or timing.get("exposure_host_stamp_s")
        binding = _binding_from_bundle(bundle)
        context = None
        if args.build_m_context:
            try:
                context = _build_m_context(req, bundle)
            except ValueError as exc:
                context_notes.append(str(exc))
        try:
            # Incomplete binding (null clock evidence) → audit reports BUNDLE_BINDING_MISSING.
            inspection, diagnostic = consume_handoff(
                handoff, bundle, binding,
                context=context,
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
            "m_context_present": context is not None,
            "calibration_hash": bundle.get("calibration_hash"),
        })

    blocked = sum(1 for c in consumption if c["diagnostic"]["status"] == "BLOCKED")
    ready = sum(1 for c in consumption if c["diagnostic"]["status"] == "SHADOW_INSPECTION_READY")
    out = {
        "schema_version": "v-slot-shadow-pipeline-0.1",
        "request": _repo_rel(args.request),
        "request_status": req.get("status"),
        "control_ready": False,
        "motion_enabled": False,
        "calibration_binding": (
            _repo_rel(args.calibration_binding) if args.calibration_binding else None
        ),
        "build_m_context": bool(args.build_m_context),
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
            "yaw remains UNKNOWN under 90deg symmetry unless MEASURED; "
            "yaw_policy=symmetric_90_unbounded may clear ERROR_BOUND_UNKNOWN without forging PASS.",
            *context_notes,
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
        "m_context": bool(args.build_m_context),
        "calibration_binding": out["calibration_binding"],
    }, indent=2))


if __name__ == "__main__":
    main()
