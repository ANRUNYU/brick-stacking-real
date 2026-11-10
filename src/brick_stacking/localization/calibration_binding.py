"""Candidate calibration → current binding (hash identity only).

A current binding fills ``calibration_hash`` for verify/context matching. It does
**not** rewrite candidate ``approved``, enable motion, raise ``control_ready``,
or claim independent accuracy validation.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any


SCHEMA = "v-calibration-current-binding-0.1"
STATUS_PENDING = "PENDING_FIELD_CHECKS"
STATUS_ACTIVE = "CURRENT_BINDING_ACTIVE"
STATUS_REVOKED = "REVOKED"

C35_DEFAULT_CANDIDATE = Path(
    "calibration/candidates/C35_left_head_fit_only_user10mm_20261108.json"
)
C35_EXPECTED_SHA256 = (
    "a8711b804660ff8888e85e07b836bb336832ab04a31bf5337e7b64157a003461"
)


def file_sha256(path: Path, *, text_lf_canonical: bool = True) -> str:
    """Hash candidate bytes. JSON text uses UTF-8 LF canonical form for cross-OS identity."""
    raw = path.read_bytes()
    if text_lf_canonical:
        # Windows checkouts may rewrite LF→CRLF; binding identity follows repo LF bytes.
        raw = raw.replace(b"\r\n", b"\n")
    return sha256(raw).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def optical_frame_for_camera(camera_serial: str) -> str:
    return f"camera_{camera_serial}_color_optical_frame"


@dataclass(frozen=True)
class BindingChecks:
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.blockers


def _repo_rel(path: Path) -> str:
    text = str(path).replace("\\", "/")
    marker = "/calibration/candidates/"
    if marker in text:
        return "calibration/candidates/" + text.split(marker, 1)[1]
    marker = "/config/"
    if marker in f"/{text}":
        # Keep config/... relative when under the repo config tree.
        idx = text.rfind("/config/")
        if idx >= 0:
            return text[idx + 1 :]
    return text


def inspect_candidate(candidate_path: Path, *, expected_sha256: str | None = None) -> dict[str, Any]:
    """Load candidate bytes + metadata without promoting approval flags."""
    digest = file_sha256(candidate_path)
    candidate = load_json(candidate_path)
    context = candidate.get("context") or {}
    report = candidate.get("report") or {}
    expected = expected_sha256 or C35_EXPECTED_SHA256
    return {
        "path": _repo_rel(candidate_path),
        "file_sha256": digest,
        "sha256_matches_expected": digest == expected,
        "expected_sha256": expected,
        "candidate_id": report.get("candidate_id") or context.get("dataset_id"),
        "camera_serial": context.get("camera_serial"),
        "camera_frame": candidate.get("camera_frame"),
        "base_frame": candidate.get("base_frame"),
        "calibration_status": candidate.get("calibration_status"),
        "independent_validation": candidate.get("independent_validation"),
        "approved": bool(candidate.get("approved")),
        "motion_enabled": bool(candidate.get("motion_enabled")),
        "execution_approval": bool(candidate.get("execution_approval")),
    }


def evaluate_activation(
    *,
    candidate_info: dict[str, Any],
    mount_continuity: dict[str, Any] | None,
    live_serial: str | None,
    operator_attest_current_binding: bool,
    require_live_serial: bool = True,
) -> BindingChecks:
    """Return blockers that keep a binding PENDING (never silent activate)."""
    blockers: list[str] = []
    warnings: list[str] = []

    if not candidate_info.get("sha256_matches_expected"):
        blockers.append("candidate_sha256_mismatch")
    if candidate_info.get("approved"):
        blockers.append("candidate_marked_approved_unexpected")
    if candidate_info.get("motion_enabled") or candidate_info.get("execution_approval"):
        blockers.append("candidate_motion_or_execution_already_true")
    serial = candidate_info.get("camera_serial")
    frame = candidate_info.get("camera_frame")
    if not serial:
        blockers.append("candidate_camera_serial_missing")
    elif frame != optical_frame_for_camera(serial):
        blockers.append("candidate_camera_frame_mismatch")

    mount = mount_continuity or {}
    if mount.get("status") != "OPERATOR_CONFIRMED_UNCHANGED_RELATIVE_TO_ROBOT_BASE":
        blockers.append("mount_continuity_not_operator_confirmed")
    if mount.get("expected_camera_serial") and serial and mount["expected_camera_serial"] != serial:
        blockers.append("mount_expected_serial_mismatch")

    if require_live_serial:
        if not live_serial:
            blockers.append("live_serial_not_checked")
        elif serial and live_serial != serial:
            blockers.append("live_serial_mismatch")
    if not operator_attest_current_binding:
        blockers.append("operator_attest_current_binding_missing")

    if candidate_info.get("independent_validation") not in (None, "NOT_PERFORMED",
                                                            "NOT_PERFORMED_AT_USER_REQUEST"):
        warnings.append(f"independent_validation={candidate_info.get('independent_validation')}")
    else:
        warnings.append("independent_validation_still_not_performed")
    warnings.append("binding_is_hash_identity_only_not_accuracy_approval")
    warnings.append("control_ready_and_motion_enabled_remain_false")
    return BindingChecks(tuple(dict.fromkeys(blockers)), tuple(dict.fromkeys(warnings)))


def build_binding_record(
    *,
    candidate_path: Path,
    expected_sha256: str | None = None,
    mount_continuity_ref: str | None,
    mount_continuity: dict[str, Any] | None,
    live_serial: str | None,
    live_serial_checked: bool,
    operator_attest_current_binding: bool,
    intake_ref: str | None = None,
    activate: bool = False,
) -> dict[str, Any]:
    info = inspect_candidate(candidate_path, expected_sha256=expected_sha256)
    checks = evaluate_activation(
        candidate_info=info,
        mount_continuity=mount_continuity,
        live_serial=live_serial if live_serial_checked else None,
        operator_attest_current_binding=operator_attest_current_binding,
    )
    status = STATUS_PENDING
    if activate and checks.ok:
        status = STATUS_ACTIVE
    elif activate and not checks.ok:
        status = STATUS_PENDING
    return {
        "schema_version": SCHEMA,
        "status": status,
        "calibration_hash": info["file_sha256"] if status == STATUS_ACTIVE else None,
        "candidate": {
            "path": info["path"],
            "file_sha256": info["file_sha256"],
            "candidate_id": info["candidate_id"],
            "calibration_status": info["calibration_status"],
            "independent_validation": info["independent_validation"],
            "approved": False,
            "motion_enabled": False,
            "status": "FIT_ONLY_NOT_AN_APPROVED_ACCURACY_CLAIM",
        },
        "identity": {
            "camera_serial": info["camera_serial"],
            "camera_frame": info["camera_frame"],
            "base_frame": info["base_frame"],
        },
        "scope": {
            "binds_hash_for_verify_and_context_matching": True,
            "does_not_approve_accuracy": True,
            "does_not_enable_motion": True,
            "does_not_set_control_ready": True,
            "does_not_rewrite_candidate_approved": True,
        },
        "evidence": {
            "intake_ref": intake_ref,
            "mount_continuity_ref": mount_continuity_ref,
            "mount_continuity_status": (mount_continuity or {}).get("status"),
            "live_serial_checked": bool(live_serial_checked and live_serial),
            "live_serial_value": live_serial if live_serial_checked else None,
            "operator_attest_current_binding": bool(operator_attest_current_binding),
            "blocking_reasons": list(checks.blockers),
            "warnings": list(checks.warnings),
        },
        "control_ready": False,
        "motion_enabled": False,
        "permit": None,
        "notes": [
            "Active binding sets calibration_hash to the candidate file sha256.",
            "Candidate approved/motion_enabled flags must stay false.",
            "Independent validation / accuracy approval are separate from current binding.",
        ],
    }


def load_binding(path: Path) -> dict[str, Any]:
    record = load_json(path)
    if record.get("schema_version") != SCHEMA:
        raise ValueError(f"unsupported calibration binding schema: {record.get('schema_version')}")
    if record.get("control_ready") is not False or record.get("motion_enabled") is not False:
        raise ValueError("calibration binding must keep control_ready/motion_enabled false")
    if (record.get("candidate") or {}).get("approved") or (record.get("candidate") or {}).get(
        "motion_enabled"
    ):
        raise ValueError("binding must not promote candidate approved/motion_enabled")
    return record


def active_calibration_hash(binding: dict[str, Any] | None) -> str | None:
    if not binding or binding.get("status") != STATUS_ACTIVE:
        return None
    digest = binding.get("calibration_hash")
    candidate_sha = (binding.get("candidate") or {}).get("file_sha256")
    if not digest or digest != candidate_sha:
        raise ValueError("active binding calibration_hash must equal candidate file_sha256")
    if binding.get("control_ready") is not False or binding.get("motion_enabled") is not False:
        raise ValueError("active binding illegally enables control/motion")
    return digest


def apply_binding_to_bundle(bundle: dict[str, Any], binding: dict[str, Any] | None) -> dict[str, Any]:
    """Return a copy with calibration_hash stamped when binding is ACTIVE and identity matches."""
    out = deepcopy(bundle)
    digest = active_calibration_hash(binding)
    if digest is None:
        return out
    rgbd = out.get("rgbd") or {}
    identity = binding.get("identity") or {}
    if rgbd.get("device_id") != identity.get("camera_serial"):
        raise ValueError("bundle camera_id does not match active binding identity")
    if rgbd.get("frame_id") != identity.get("camera_frame"):
        raise ValueError("bundle frame_id does not match active binding identity")
    if out.get("control_ready") is not False:
        raise ValueError("refusing to stamp calibration_hash onto control_ready bundle")
    existing = out.get("calibration_hash")
    if existing not in (None, "", digest):
        raise ValueError("bundle already has a different calibration_hash")
    out["calibration_hash"] = digest
    out["control_ready"] = False
    return out


def apply_binding_to_request(request: dict[str, Any], binding: dict[str, Any] | None) -> dict[str, Any]:
    """Copy request; fill calibration_hash only when binding is ACTIVE."""
    out = deepcopy(request)
    digest = active_calibration_hash(binding)
    out["control_ready"] = False
    out["motion_enabled"] = False
    out["permit"] = None
    if digest is None:
        return out
    existing = out.get("calibration_hash")
    if existing not in (None, "", digest):
        raise ValueError("request already has a different calibration_hash")
    out["calibration_hash"] = digest
    candidate = out.setdefault("calibration_candidate", {})
    candidate["file_sha256"] = (binding.get("candidate") or {}).get("file_sha256")
    candidate["path"] = (binding.get("candidate") or {}).get("path")
    candidate["status"] = "BOUND_AS_CURRENT_HASH_IDENTITY_ONLY"
    out["status"] = "SHADOW_ADOPTED_CAMERA_EXPECTATIONS_CURRENT_CALIBRATION_BOUND"
    notes = list(out.get("notes") or [])
    notes.append(
        "calibration_hash is the active current-binding identity; not accuracy/motion approval."
    )
    out["notes"] = notes
    return out
