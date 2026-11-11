"""Dry-run / arm-disabled SafetyGate issuance diagnostic."""
from __future__ import annotations

from pathlib import Path

import pytest

from brick_stacking.arm.adapter import MockArm
from brick_stacking.execution.safety_gate import (
    PROBE_TRAJECTORY_HASH,
    OfflineSafetyGate,
)
from brick_stacking.runtime.config_loader import load_config

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "config/offline_task.yaml"


@pytest.fixture
def gate_and_arm():
    config = load_config(CONFIG)
    gate = OfflineSafetyGate(max_age_s=float(config["task"]["max_observation_age_s"]))
    arm = MockArm((0.0,) * 7, device_id="mock-arm-dry-run-test")
    return gate, arm


def test_issue_dry_run_lists_missing_trajectory_hash(gate_and_arm):
    gate, arm = gate_and_arm
    report = gate.issue_dry_run_diagnostic(
        arm=arm,
        config_hash="cfg-hash",
        calibration_hash="cal-hash",
        scene_version="scene-v1",
        trajectory_hash=None,
    )
    assert report["executable"] is False
    assert report["live_permit"] is None
    assert report["control_ready"] is False
    assert report["issuance_attempted"] is True
    assert report["issuance_fields_complete"] is False
    assert report["only_hardware_enable_and_policy_remaining"] is False
    assert "trajectory_hash" in report["still_missing_fields"]
    assert report["blocked_by"][0] == "trajectory_hash"
    assert "j6_j7_readonly" in report["blocked_by"]
    assert "awaiting_live_arm" in report["blocked_by"]
    assert report["live_permit_path_status"] == "fields_incomplete"
    assert report["field_status"]["device_id"]["status"] == "PRESENT_FROM_MOCK_ARM"
    assert report["field_status"]["valid_until_host_monotonic_s"]["status"] == (
        "PRESENT_FROM_ISSUANCE_CLOCK"
    )
    assert report["field_status"]["trajectory_hash"]["status"] == "MISSING_PLAN_BUNDLE"
    assert report["draft_permit"] is None
    plumbing = report["plumbing_self_check"]
    assert plumbing["gate_accepts_complete_dry_run_permit"] is True
    assert plumbing["probe_trajectory_hash"] == PROBE_TRAJECTORY_HASH


def test_issue_dry_run_complete_fields_gate_accepts(gate_and_arm):
    gate, arm = gate_and_arm
    report = gate.issue_dry_run_diagnostic(
        arm=arm,
        config_hash="cfg-hash",
        calibration_hash="cal-hash",
        scene_version="scene-v1",
        trajectory_hash="plan-bundle-hash-fixture",
    )
    assert report["issuance_fields_complete"] is True
    assert report["executable"] is False
    assert report["live_permit"] is None
    assert report["gate_accepts_draft"] is True
    assert report["only_hardware_enable_and_policy_remaining"] is True
    assert report["still_missing_fields"] == []
    assert report["blocked_by"] == ["j6_j7_readonly", "awaiting_live_arm"]
    assert report["live_permit_path_status"] == "software_exhausted_awaiting_live_arm"
    assert "j6_j7_readonly" in report["still_missing_for_formal"]
    assert "awaiting_live_arm" in report["still_missing_for_formal"]
    assert report["authority"]["hard_block_id"] == (
        "j6_j7_no_audited_readonly_position_query"
    )
    draft = report["draft_permit"]
    assert draft is not None
    assert draft["trajectory_hash"] == "plan-bundle-hash-fixture"
    assert draft["device_id"] == "mock-arm-dry-run-test"


def test_issue_dry_run_rejects_hardware_enabled_arm(gate_and_arm):
    gate, _ = gate_and_arm

    class _BadArm:
        backend = "mock"
        hardware_enabled = True

        def read_state(self):
            return {}

    with pytest.raises(ValueError, match="hardware_enabled=False"):
        gate.issue_dry_run_diagnostic(arm=_BadArm(), config_hash="c")
