"""Prepare / activate C35 (or other candidate) as current calibration_hash binding.

Does not open arm/CAN. Never sets control_ready or motion_enabled.
Activation requires live serial check + explicit operator attest flags.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src")]

from brick_stacking.localization.calibration_binding import (  # noqa: E402
    C35_DEFAULT_CANDIDATE,
    C35_EXPECTED_SHA256,
    STATUS_ACTIVE,
    STATUS_PENDING,
    build_binding_record,
    load_json,
)


DEFAULT_INTAKE = ROOT / "config/observed/first_placement_reference_intake_20261110.json"
DEFAULT_OUT = ROOT / "config/observed/calibration_current_binding_c35_20261110.json"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candidate", type=Path, default=ROOT / C35_DEFAULT_CANDIDATE)
    p.add_argument("--expected-sha256", default=C35_EXPECTED_SHA256)
    p.add_argument("--intake", type=Path, default=DEFAULT_INTAKE)
    p.add_argument("--output", type=Path, default=DEFAULT_OUT)
    p.add_argument("--live-serial", default=None,
                   help="Camera SN observed on the live host (field check).")
    p.add_argument("--attest-live-serial", action="store_true",
                   help="Operator attests --live-serial was read from the live device.")
    p.add_argument("--attest-current-binding", action="store_true",
                   help="Operator attests this candidate sha is the current binding identity.")
    p.add_argument("--activate", action="store_true",
                   help="Attempt ACTIVE status; stays PENDING if blockers remain.")
    p.add_argument("--write", action="store_true",
                   help="Write the binding JSON (refuses overwrite unless --force).")
    p.add_argument("--force", action="store_true")
    p.add_argument("--update-adopted-request", action="store_true",
                   help="If ACTIVE, also stamp calibration_hash into adopted request.")
    p.add_argument(
        "--adopted-request",
        type=Path,
        default=ROOT / "config/planning/first_placement_review_request.adopted.json",
    )
    args = p.parse_args(argv)

    intake = load_json(args.intake) if args.intake.exists() else {}
    mount = intake.get("camera_mount_continuity") or {}
    live_checked = bool(args.attest_live_serial and args.live_serial)

    def _rel(path: Path | None) -> str | None:
        if path is None or not path.exists():
            return None
        try:
            return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
        except ValueError:
            return str(path).replace("\\", "/")

    record = build_binding_record(
        candidate_path=args.candidate,
        expected_sha256=args.expected_sha256,
        mount_continuity_ref=_rel(args.intake),
        mount_continuity=mount,
        live_serial=args.live_serial,
        live_serial_checked=live_checked,
        operator_attest_current_binding=bool(args.attest_current_binding),
        intake_ref=_rel(args.intake),
        activate=bool(args.activate),
    )
    summary = {
        "status": record["status"],
        "calibration_hash": record["calibration_hash"],
        "blocking_reasons": record["evidence"]["blocking_reasons"],
        "warnings": record["evidence"]["warnings"],
        "control_ready": False,
        "motion_enabled": False,
        "output": str(args.output).replace("\\", "/"),
        "wrote": False,
        "adopted_updated": False,
    }

    if args.write:
        if args.output.exists() and not args.force:
            raise SystemExit(f"output exists (pass --force): {args.output}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        summary["wrote"] = True
        # Keep intake pointer in sync without inventing an active hash.
        if args.intake.exists():
            intake_out = dict(intake)
            cand = dict(intake_out.get("calibration_candidate") or {})
            cand["current_session_binding"] = _rel(args.output)
            intake_out["calibration_candidate"] = cand
            if live_checked:
                mount_out = dict(intake_out.get("camera_mount_continuity") or {})
                mount_out["current_device_serial_checked"] = True
                mount_out["current_device_serial"] = args.live_serial
                intake_out["camera_mount_continuity"] = mount_out
            intake_out["control_ready"] = False
            intake_out["motion_enabled"] = False
            args.intake.write_text(json.dumps(intake_out, indent=2) + "\n", encoding="utf-8")

    if args.update_adopted_request:
        if record["status"] != STATUS_ACTIVE or not record["calibration_hash"]:
            summary["adopted_update_blocked"] = list(record["evidence"]["blocking_reasons"]) or [
                "binding_not_active"
            ]
        else:
            from brick_stacking.localization.calibration_binding import (
                apply_binding_to_request,
                load_binding,
            )
            # Prefer freshly built record; re-validate via load path after write.
            binding = record if not summary["wrote"] else load_binding(args.output)
            req = load_json(args.adopted_request)
            updated = apply_binding_to_request(req, binding)
            updated["calibration_binding_path"] = str(args.output).replace("\\", "/")
            if args.write or args.force:
                args.adopted_request.write_text(
                    json.dumps(updated, indent=2) + "\n", encoding="utf-8"
                )
                summary["adopted_updated"] = True
            else:
                summary["adopted_preview_status"] = updated.get("status")
                summary["adopted_preview_calibration_hash"] = updated.get("calibration_hash")

    if record["status"] == STATUS_PENDING and args.activate:
        summary["activation_result"] = "blocked"
    elif record["status"] == STATUS_ACTIVE:
        summary["activation_result"] = "active"
    else:
        summary["activation_result"] = "pending"

    print(json.dumps(summary, indent=2))
    return 0 if (not args.activate or record["status"] == STATUS_ACTIVE) else 2


if __name__ == "__main__":
    raise SystemExit(main())
