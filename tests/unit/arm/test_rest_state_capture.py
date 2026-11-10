"""Default-off Rest state capture gate (mock only; no CAN / no Rest send)."""
from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

from brick_stacking.arm.arm_state_validity import classify_arm_state
from brick_stacking.arm.rest_state_capture import (
    ENV_VAR,
    RestStateCaptureDisabled,
    build_live_valid_draft_from_rest,
    is_rest_state_capture_draft,
    is_rest_state_capture_enabled,
    rest_state_capture_gate_report,
)
from brick_stacking.execution.host_control_readiness import evaluate_host_control_readiness

ROOT = Path(__file__).resolve().parents[3]
GAPS = ROOT / "docs/team/B/evidence/field_20261110/pre_grasp_gaps_20261110.json"
DIAG = (
    ROOT
    / "docs/team/B/evidence/field_20261110/diagnostic_permit_eligibility_20261110.json"
)
PLAN = ROOT / "docs/team/B/evidence/field_20261110/shadow_plan_bundle_20261110.json"
ARM = (
    ROOT
    / "docs/team/B/evidence/field_20261110/recorded_arm_state_left_p7_20261110.json"
)


def _mock_rest_capture() -> dict:
    """Synthetic Rest capture: J1–J5 float rad + J6/J7 U16 raw (no bus)."""
    received = []
    for mid, q in zip(range(61, 66), (0.01, 0.02, 0.03, 0.04, 0.05), strict=True):
        received.append(
            {
                "motor_id": mid,
                "position_sdk_rad": q,
                "host_receive_monotonic_s": float(mid - 61),
            }
        )
    # U16 mid-scale → mid of [0, 1] profile = 0.5
    for mid, u16 in ((66, 32767), (67, 32767)):
        received.append(
            {
                "motor_id": mid,
                "position_raw_u16": u16,
                "status": 0,
                "fault": 0,
                "host_receive_monotonic_s": float(mid - 61),
                "raw_hex": (
                    bytes([0]) + int(u16).to_bytes(2, "big") + bytes([0, 0, 0, 0, 0])
                ).hex(),
            }
        )
    return {
        "schema_version": "c-left-supported-rest-1",
        "source": "real",
        "arm_role": "left",
        "interface": "can2",
        "status": "RAW_SEVEN_AXIS_CAPTURED",
        "clock_domain": "host_monotonic",
        "epoch": "linux_boot:mock-rest-test",
        "authorization_ref": "unit-test-only",
        "received": received,
    }


def _mock_range_profile() -> dict:
    return {
        "66": {
            "verified": True,
            "evidence": "synthetic-test-only",
            "units": "rad",
            "theta_min_rad": 0.0,
            "theta_max_rad": 1.0,
        },
        "67": {
            "verified": True,
            "evidence": "synthetic-test-only",
            "units": "rad",
            "theta_min_rad": 0.0,
            "theta_max_rad": 1.0,
        },
    }


def test_gate_default_closed():
    assert is_rest_state_capture_enabled(cli_flag=False, environ={}) is False
    report = rest_state_capture_gate_report(enabled=False)
    assert report["rest_state_capture_available"] is True
    assert report["rest_state_capture_enabled"] is False
    assert report["blocked_unless_rest_attested"] is True
    assert report["raises_formal_grasp_entry_allowed"] is False
    assert report["raises_control_ready"] is False
    assert report["ci_never_auto_rest"] is True


def test_gate_opens_via_cli_or_env():
    assert is_rest_state_capture_enabled(cli_flag=True, environ={}) is True
    assert (
        is_rest_state_capture_enabled(cli_flag=False, environ={ENV_VAR: "1"}) is True
    )
    assert (
        is_rest_state_capture_enabled(cli_flag=False, environ={ENV_VAR: "yes"}) is True
    )


def test_closed_gate_refuses_draft_behavior_unchanged():
    with pytest.raises(RestStateCaptureDisabled):
        build_live_valid_draft_from_rest(
            _mock_rest_capture(),
            rest_state_capture=False,
            range_profile=_mock_range_profile(),
        )


def test_open_gate_builds_live_valid_draft_from_rest():
    payload = build_live_valid_draft_from_rest(
        _mock_rest_capture(),
        rest_state_capture=True,
        range_profile=_mock_range_profile(),
    )
    state = payload["arm_state"]
    classified = classify_arm_state(state)
    assert is_rest_state_capture_draft(state) is True
    assert classified["counts_as_live_valid"] is True
    assert payload["counts_as_live_valid"] is True
    assert state["source"] == "real"
    assert state["validity"] == "VALID"
    assert len(state["q_rad"]) == 7
    assert all(isinstance(q, float) for q in state["q_rad"])
    assert state["rest_state_capture"]["counts_as_formal_live_valid"] is False
    assert payload["control_ready"] is False
    assert payload["motion_enabled"] is False


def test_rest_draft_does_not_auto_raise_formal_grasp():
    draft = build_live_valid_draft_from_rest(
        _mock_rest_capture(),
        rest_state_capture=True,
        range_profile=_mock_range_profile(),
    )
    gaps = json.loads(GAPS.read_text(encoding="utf-8"))
    diag = json.loads(DIAG.read_text(encoding="utf-8"))
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    report = evaluate_host_control_readiness(
        pre_grasp_gaps=gaps,
        diagnostic_permit=diag,
        plan_bundle=plan,
        arm_state=draft["arm_state"],
        probe_dry_run=True,
        config_path=ROOT / "config/offline_task.yaml",
        rest_state_capture=True,
    )
    payload = report.to_dict()
    ladder = payload["gate_ladder"]
    assert ladder["rest_state_capture_available"] is True
    assert ladder["rest_state_capture_enabled"] is True
    assert ladder["blocked_unless_rest_attested"] is False
    assert ladder["rest_state_capture_draft"] is True
    assert ladder["structural_counts_as_live_valid"] is True
    assert ladder["counts_as_live_valid"] is False  # Rest ≠ formal audited live
    assert payload["formal_grasp_entry_allowed"] is False
    assert payload["control_ready"] is False
    assert payload["formal_grasp_blocked_by"] == ["j6_j7_readonly", "awaiting_live_arm"]
    by_id = {item.id: item for item in report.checklist}
    assert by_id["live_valid_arm_state"].status == "POLICY_HOLD"
    assert by_id["rest_state_capture_gate"].status == "PASS"


def test_readiness_default_path_blocked_unless_rest_attested():
    gaps = json.loads(GAPS.read_text(encoding="utf-8"))
    diag = json.loads(DIAG.read_text(encoding="utf-8"))
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    arm = json.loads(ARM.read_text(encoding="utf-8"))
    report = evaluate_host_control_readiness(
        pre_grasp_gaps=gaps,
        diagnostic_permit=diag,
        plan_bundle=plan,
        arm_state=arm,
        probe_dry_run=True,
        config_path=ROOT / "config/offline_task.yaml",
        rest_state_capture=False,
    )
    ladder = report.to_dict()["gate_ladder"]
    assert ladder["rest_state_capture_available"] is True
    assert ladder["rest_state_capture_enabled"] is False
    assert ladder["blocked_unless_rest_attested"] is True
    assert ladder["formal_grasp_entry_allowed"] is False
    assert ladder["control_ready"] is False


def test_cli_rest_draft_requires_gate(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    capture_path = tmp_path / "rest.json"
    profile_path = tmp_path / "range.json"
    out = tmp_path / "draft.json"
    capture_path.write_text(json.dumps(_mock_rest_capture()), encoding="utf-8")
    profile_path.write_text(json.dumps(_mock_range_profile()), encoding="utf-8")
    mod = runpy.run_path(str(ROOT / "tools/arm_state_live_or_recorded.py"))
    with pytest.raises(SystemExit):
        mod["main"](
            [
                "--mode",
                "rest-draft",
                "--rest-capture",
                str(capture_path),
                "--range-profile",
                str(profile_path),
                "--output",
                str(out),
            ]
        )
    assert not out.exists()

    rc = mod["main"](
        [
            "--mode",
            "rest-draft",
            "--rest-state-capture",
            "--rest-capture",
            str(capture_path),
            "--range-profile",
            str(profile_path),
            "--output",
            str(out),
        ]
    )
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["counts_as_live_valid"] is True
    assert payload["control_ready"] is False
    assert payload["rest_state_capture"]["rest_state_capture_enabled"] is True
