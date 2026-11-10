"""Current calibration binding: hash identity only; never motion/control promotion."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from brick_stacking.localization.calibration_binding import (
    C35_DEFAULT_CANDIDATE,
    C35_EXPECTED_SHA256,
    STATUS_ACTIVE,
    STATUS_PENDING,
    active_calibration_hash,
    apply_binding_to_bundle,
    apply_binding_to_request,
    build_binding_record,
    evaluate_activation,
    inspect_candidate,
)


ROOT = Path(__file__).resolve().parents[3]
CANDIDATE = ROOT / C35_DEFAULT_CANDIDATE
INTAKE = ROOT / "config/observed/first_placement_reference_intake_20261110.json"


def _mount():
    return json.loads(INTAKE.read_text(encoding="utf-8"))["camera_mount_continuity"]


def test_inspect_c35_candidate_bytes_match_declared_sha():
    info = inspect_candidate(CANDIDATE)
    assert info["file_sha256"] == C35_EXPECTED_SHA256
    assert info["sha256_matches_expected"] is True
    assert info["approved"] is False
    assert info["motion_enabled"] is False
    assert info["camera_serial"] == "CP2L863000KL"
    assert info["camera_frame"] == "camera_CP2L863000KL_color_optical_frame"
    # Raw Windows CRLF bytes may differ; binding identity is LF-canonical.
    from brick_stacking.localization.calibration_binding import file_sha256
    raw = file_sha256(CANDIDATE, text_lf_canonical=False)
    if b"\r\n" in CANDIDATE.read_bytes():
        assert raw != C35_EXPECTED_SHA256
    assert info["file_sha256"] == C35_EXPECTED_SHA256


def test_activation_blocked_without_live_serial_and_attest():
    info = inspect_candidate(CANDIDATE)
    checks = evaluate_activation(
        candidate_info=info,
        mount_continuity=_mount(),
        live_serial=None,
        operator_attest_current_binding=False,
    )
    assert not checks.ok
    assert "live_serial_not_checked" in checks.blockers
    assert "operator_attest_current_binding_missing" in checks.blockers


def test_build_pending_record_keeps_null_hash_and_false_gates():
    record = build_binding_record(
        candidate_path=CANDIDATE,
        mount_continuity_ref=str(INTAKE).replace("\\", "/"),
        mount_continuity=_mount(),
        live_serial=None,
        live_serial_checked=False,
        operator_attest_current_binding=False,
        intake_ref=str(INTAKE).replace("\\", "/"),
        activate=True,
    )
    assert record["status"] == STATUS_PENDING
    assert record["calibration_hash"] is None
    assert record["control_ready"] is False
    assert record["motion_enabled"] is False
    assert record["candidate"]["approved"] is False
    assert active_calibration_hash(record) is None


def test_active_binding_stamps_request_and_bundle():
    record = build_binding_record(
        candidate_path=CANDIDATE,
        mount_continuity_ref=str(INTAKE).replace("\\", "/"),
        mount_continuity=_mount(),
        live_serial="CP2L863000KL",
        live_serial_checked=True,
        operator_attest_current_binding=True,
        activate=True,
    )
    assert record["status"] == STATUS_ACTIVE
    assert record["calibration_hash"] == C35_EXPECTED_SHA256
    assert record["control_ready"] is False

    req = json.loads(
        (ROOT / "config/planning/first_placement_review_request.adopted.json").read_text(
            encoding="utf-8"
        )
    )
    stamped = apply_binding_to_request(req, record)
    assert stamped["calibration_hash"] == C35_EXPECTED_SHA256
    assert stamped["control_ready"] is False
    assert stamped["motion_enabled"] is False
    assert stamped["calibration_candidate"]["status"] == "BOUND_AS_CURRENT_HASH_IDENTITY_ONLY"

    field = ROOT / "docs/team/B/evidence/field_20261110/verify_pre_grasp_observation_bundles.jsonl"
    bundle = json.loads(next(line for line in field.read_text(encoding="utf-8").splitlines() if line.strip()))
    out = apply_binding_to_bundle(bundle, record)
    assert out["calibration_hash"] == C35_EXPECTED_SHA256
    assert out["control_ready"] is False
    assert bundle.get("calibration_hash") in (None, "")


def test_apply_binding_rejects_camera_mismatch():
    record = build_binding_record(
        candidate_path=CANDIDATE,
        mount_continuity=_mount(),
        mount_continuity_ref=None,
        live_serial="CP2L863000KL",
        live_serial_checked=True,
        operator_attest_current_binding=True,
        activate=True,
    )
    assert record["status"] == STATUS_ACTIVE
    bundle = {
        "rgbd": {"device_id": "OTHER", "frame_id": record["identity"]["camera_frame"]},
        "control_ready": False,
        "calibration_hash": None,
    }
    with pytest.raises(ValueError, match="camera_id"):
        apply_binding_to_bundle(bundle, record)


def test_template_request_still_unbound():
    target = json.loads(
        (ROOT / "config/planning/first_placement_review_request.template.json").read_text(
            encoding="utf-8"
        )
    )
    assert target["calibration_hash"] is None
    assert target["calibration_candidate"]["status"] == "FIT_ONLY_NOT_AN_APPROVED_CURRENT_BINDING"
