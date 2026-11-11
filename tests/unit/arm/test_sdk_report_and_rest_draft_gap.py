"""SDK-report wrist angles + honest rest-draft GAP (no verified forge)."""
from __future__ import annotations

import json
from pathlib import Path

from brick_stacking.arm.rest_state_capture import (
    SDK_REPORT_PROVENANCE,
    annotate_sdk_report_wrist_angles,
    attempt_rest_draft_or_gap,
    sdk_default_u16_to_rad,
)
from brick_stacking.execution.t1_bounded_live_runner import (
    build_t1_bounded_dry_plan,
    evaluate_t1_prerequisites,
)

ROOT = Path(__file__).resolve().parents[3]
LIVE_CAPTURE = ROOT / "docs/team/B/evidence/left_supported_rest_20261111_011818.json"
RANGE_PROFILE = ROOT / "calibration/measurement_templates/left_wrist_theta_ranges.json"


def test_sdk_default_midscale_near_zero():
    # 32768/65535 * 25 - 12.5 ≈ +0.00019
    q = sdk_default_u16_to_rad(32768)
    assert abs(q) < 0.001


def test_annotate_sdk_report_from_live_capture():
    capture = json.loads(LIVE_CAPTURE.read_text(encoding="utf-8"))
    report = annotate_sdk_report_wrist_angles(capture)
    assert report["audited_range_profile"] is False
    assert report["may_mark_left_wrist_theta_ranges_verified"] is False
    assert report["wrist"]["66"]["provenance"] == SDK_REPORT_PROVENANCE
    assert report["wrist"]["66"]["position_raw_u16"] == 32622
    assert report["wrist"]["67"]["position_raw_u16"] == 33179
    assert report["wrist"]["66"]["equals_verified_left_wrist_theta_ranges"] is False


def test_attempt_rest_draft_gap_with_unverified_profile():
    capture = json.loads(LIVE_CAPTURE.read_text(encoding="utf-8"))
    profile = json.loads(RANGE_PROFILE.read_text(encoding="utf-8"))
    assert profile["66"]["verified"] is False
    out = attempt_rest_draft_or_gap(
        capture,
        range_profile=profile,
        rest_state_capture=True,
        attest_rest_for_pregrasp=True,
    )
    assert out["pass"] is False
    assert out["verdict"] == "GAP_UNVERIFIED_RANGE_OR_DECODE"
    assert out["control_ready"] is False
    assert out["honest_non_pass"] is True
    assert out["sdk_report_angles"]["wrist"]["66"]["position_sdk_report_rad"] is not None


def test_t1_prereq_allows_dry_plan_without_motion():
    capture = json.loads(LIVE_CAPTURE.read_text(encoding="utf-8"))
    profile = json.loads(RANGE_PROFILE.read_text(encoding="utf-8"))
    attempt = attempt_rest_draft_or_gap(
        capture,
        range_profile=profile,
        rest_state_capture=True,
        attest_rest_for_pregrasp=False,
    )
    prereq = evaluate_t1_prerequisites(
        rest_capture=capture,
        rest_draft_attempt=attempt,
        range_profile=profile,
        urdf_available=True,
    )
    assert prereq["subset_dry_plan_allowed"] is True
    assert prereq["live_motion_allowed"] is False
    assert prereq["control_ready"] is False
    assert "j6_j7_range_profile_unverified" in prereq["blocked_by"]
    plan = build_t1_bounded_dry_plan(rest_capture=capture, prerequisites=prereq)
    assert plan["executable"] is False
    assert plan["motion_enabled"] is False
    assert plan["wrist_j6_j7_commanded"] is False
