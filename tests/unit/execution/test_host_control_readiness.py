"""Host/safety checklist: report gaps; never raise control_ready / enable motion."""
from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

from brick_stacking.execution.host_control_readiness import (
    evaluate_host_control_readiness,
    probe_dry_run_arm_disabled,
)

ROOT = Path(__file__).resolve().parents[3]
GAPS = (
    ROOT
    / "docs/team/B/evidence/field_20261110/pre_grasp_gaps_20261110.json"
)
DIAG = (
    ROOT
    / "docs/team/B/evidence/field_20261110/diagnostic_permit_eligibility_20261110.json"
)


def test_probe_dry_run_arm_disabled_no_can_no_control_ready():
    probe = probe_dry_run_arm_disabled(config_path=ROOT / "config/offline_task.yaml")
    assert probe["reachable"] is True
    assert probe["mock_arm"]["hardware_enabled"] is False
    assert probe["mock_arm"]["backend"] == "mock"
    assert probe["step_without_permit_rejected"] is True
    assert probe["control_ready"] is False
    assert probe["motion_enabled"] is False
    assert probe["commands_sent"] == 0
    assert probe["can_opened"] is False


def test_field_gaps_show_not_only_operator_enable():
    gaps = json.loads(GAPS.read_text(encoding="utf-8"))
    diag = json.loads(DIAG.read_text(encoding="utf-8"))
    report = evaluate_host_control_readiness(
        pre_grasp_gaps=gaps,
        diagnostic_permit=diag,
        probe_dry_run=True,
        config_path=ROOT / "config/offline_task.yaml",
    )
    payload = report.to_dict()
    assert payload["control_ready"] is False
    assert payload["motion_enabled"] is False
    assert payload["formal_grasp_ready"] is False
    assert payload["formal_grasp_entry_allowed"] is False
    assert payload["live_permit"] is None
    assert payload["vision_pre_grasp_ready"] is True
    assert payload["permit_eligible"] is True
    assert payload["only_operator_enable_remaining"] is False
    assert payload["needs_operator_physical_enable_now"] is False
    assert payload["needs_operator_physical_enable_before_real_motion"] is True
    assert "plan_bundle_trajectory_hash" in payload["missing_software"]
    assert "arm_state_device_id" in payload["missing_software"]
    assert "live_permit" in payload["missing_field_or_operator"]
    assert "host_policy_control_ready" in payload["missing_field_or_operator"]
    assert payload["dry_run_arm_disabled"]["reachable"] is True
    by_id = {item.id: item for item in report.checklist}
    assert by_id["vision_pre_grasp_ready"].status == "PASS"
    assert by_id["live_permit"].status == "MISSING"
    assert by_id["host_policy_control_ready"].status == "POLICY_HOLD"
    assert by_id["dry_run_arm_disabled_path"].status == "PROBED"


def test_refuses_spurious_live_permit_input():
    report = evaluate_host_control_readiness(
        pre_grasp_gaps={"vision_pre_grasp_ready": True, "permit_eligible": True},
        live_permit={"device_id": "should-not-count"},
    )
    by_id = {item.id: item for item in report.checklist}
    assert by_id["live_permit"].status == "FAIL"
    assert report.to_dict()["control_ready"] is False
    assert report.to_dict()["live_permit"] is None


def test_cli_writes_report(tmp_path):
    out = tmp_path / "host_ready.json"
    mod = runpy.run_path(str(ROOT / "tools/host_control_readiness.py"))
    rc = mod["main"](
        [
            "--pre-grasp-gaps",
            str(GAPS),
            "--diagnostic-permit",
            str(DIAG),
            "--probe-dry-run-arm-disabled",
            "--config",
            str(ROOT / "config/offline_task.yaml"),
            "--output",
            str(out),
        ]
    )
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "host-control-readiness-0.1"
    assert payload["control_ready"] is False
    assert payload["motion_enabled"] is False
    assert payload["only_operator_enable_remaining"] is False
    assert payload["dry_run_arm_disabled"]["reachable"] is True
    assert payload["formal_grasp_ready"] is False
