"""Tests for left wrist-path player: dry-run, auth refusal, no finger cmds."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from brick_stacking.wrist_handoff.wrist_path_player import (
    MOTION_BACKEND_KIND,
    SPEED_LIMIT_MODE,
    RecordingSevenAxisArm,
    evaluate_live_authorization,
    file_sha256_lf,
    parse_q_rad_from_state,
    plan_step_velocity_limits,
    play_wrist_path,
    validate_path_static,
)

ROOT = Path(__file__).resolve().parents[3]
PATH_215245 = ROOT / "docs/team/P/evidence/wrist_path_layer1_grasp_to_place_20261111_215245.json"
EXPECTED_LF = "349adb65352c820dc13ece77da26b575b269ab31af821244ec60e426758d16a3"
URDF = ROOT / "config/models/p7_left/p7__left.urdf"


@pytest.fixture(scope="module")
def path_doc() -> dict:
    return json.loads(PATH_215245.read_text(encoding="utf-8-sig"))


def test_official_path_lf_hash_matches():
    assert file_sha256_lf(PATH_215245) == EXPECTED_LF


def test_dry_run_215245_assume_at_start(path_doc):
    report = play_wrist_path(
        path_file=PATH_215245,
        expected_sha256_lf=EXPECTED_LF,
        urdf_path=URDF,
        assume_at_path_start=True,
        enable_live_motion=False,
    )
    assert report["verdict"] == "DRY_RUN_OK"
    assert report["motion_started"] is False
    assert report["finger_commands_issued"] is False
    assert report["hand_touched"] is False
    assert report["rest_issued"] is False
    assert report["right_arm_commands_issued"] is False
    assert report["single_joint_moves"] is False
    assert report["path_file_mutated"] is False
    assert report["motion_backend_kind"] == MOTION_BACKEND_KIND
    assert report["static_validation"]["path_flags"]["executable"] is False
    assert report["static_validation"]["path_flags"]["motion_enabled"] is False
    assert report["static_validation"]["path_flags"]["control_ready"] is False
    assert report["joint_audit"]["J6"] == "sdk_report_not_audited"
    assert report["joint_audit"]["J7"] == "sdk_report_not_audited"
    assert report["start_precheck"]["ok"] is True
    assert report["start_precheck"]["error_m"] <= 0.01 + 1e-9
    # Evidence file on disk must remain non-executable.
    disk = json.loads(PATH_215245.read_text(encoding="utf-8-sig"))
    assert disk["executable"] is False
    assert disk["motion_enabled"] is False
    assert disk["control_ready"] is False
    assert path_doc["request_sha256"] == (
        "10ccea75df2472b2a10cf05901316a6cd68bcacf28cf7309db4386de700cda07"
    )


def test_refuse_live_without_authorization_ref():
    gate = evaluate_live_authorization(
        enable_live_motion=True, authorization_ref="  "
    )
    assert gate["live_dispatch_allowed"] is False
    assert "missing_authorization_ref" in gate["blocked_by"]

    doc = json.loads(PATH_215245.read_text(encoding="utf-8-sig"))
    q0 = list(doc["segments"][0]["points"][0]["q_rad"])
    report = play_wrist_path(
        path_file=PATH_215245,
        expected_sha256_lf=EXPECTED_LF,
        urdf_path=URDF,
        current_q_rad=q0,
        enable_live_motion=True,
        authorization_ref="",
    )
    assert report["verdict"] == "REFUSE_LIVE_AUTHORIZATION"
    assert report["motion_started"] is False
    assert report["finger_commands_issued"] is False
    assert "missing_authorization_ref" in report["blocked_by"]


def test_refuse_live_without_enable_switch():
    gate = evaluate_live_authorization(
        enable_live_motion=False, authorization_ref="field-auth-x"
    )
    assert gate["live_dispatch_allowed"] is False
    assert "missing_enable_live_motion" in gate["blocked_by"]


def test_dry_run_allows_assume_but_live_plus_assume_refuses_without_motion():
    dry = play_wrist_path(
        path_file=PATH_215245,
        expected_sha256_lf=EXPECTED_LF,
        urdf_path=URDF,
        assume_at_path_start=True,
        enable_live_motion=False,
    )
    assert dry["verdict"] == "DRY_RUN_OK"
    assert dry["motion_started"] is False
    assert dry["start_precheck"]["q_source"] == "assume_at_path_start"

    live = play_wrist_path(
        path_file=PATH_215245,
        expected_sha256_lf=EXPECTED_LF,
        urdf_path=URDF,
        assume_at_path_start=True,
        enable_live_motion=True,
        authorization_ref="unit-test-auth-not-field",
    )
    assert live["verdict"] == "REFUSE_ASSUME_AT_START_ON_LIVE"
    assert live["motion_started"] is False
    assert live["moves_dispatched"] == 0
    assert live["finger_commands_issued"] is False
    assert "assume_at_path_start_forbidden_when_enable_live_motion" in live["blocked_by"]


def test_refuse_start_pose_farther_than_10mm():
    doc = json.loads(PATH_215245.read_text(encoding="utf-8-sig"))
    q0 = list(doc["segments"][0]["points"][0]["q_rad"])
    q0[0] += 0.25  # large J1 offset → tip leaves 10 mm gate
    report = play_wrist_path(
        path_file=PATH_215245,
        expected_sha256_lf=EXPECTED_LF,
        urdf_path=URDF,
        current_q_rad=q0,
        enable_live_motion=False,
    )
    assert report["verdict"] == "REFUSE_START_POSE"
    assert report["motion_started"] is False
    assert report["start_precheck"]["approach_path_invented"] is False
    assert report["start_precheck"]["error_m"] > 0.01


def test_null_j6_j7_from_host_monitor_snapshot_refused():
    snapshot = {
        "arms": {
            "left": {
                "q_rad": [0.1, -0.05, 0.0, -1.0, 1.5, None, None],
            }
        }
    }
    with pytest.raises(ValueError, match="null"):
        parse_q_rad_from_state(snapshot)


def test_recording_live_play_is_seven_axis_and_never_touches_hand():
    doc = json.loads(PATH_215245.read_text(encoding="utf-8-sig"))
    q0 = list(doc["segments"][0]["points"][0]["q_rad"])
    arm = RecordingSevenAxisArm(initial_q_rad=q0)
    report = play_wrist_path(
        path_file=PATH_215245,
        expected_sha256_lf=EXPECTED_LF,
        urdf_path=URDF,
        current_q_rad=q0,
        enable_live_motion=True,
        authorization_ref="unit-test-auth-not-field",
        arm=arm,
    )
    assert report["verdict"] == "LIVE_PLAY_OK"
    assert report["completed"] is True
    assert report["motion_started"] is True
    assert report["finger_commands_issued"] is False
    assert report["hand_touched"] is False
    assert report["rest_issued"] is False
    assert report["right_arm_commands_issued"] is False
    assert report["single_joint_moves"] is False
    assert report["post_move_sleep_used"] is False
    assert report["speed_limit_mode"] == SPEED_LIMIT_MODE
    assert arm.hand_commands == []
    assert arm.rest_commands == []
    assert arm.right_arm_commands == []
    assert arm.enable_calls == 1
    assert report["recording"]["all_moves_seven_axis"] is True
    assert report["recording"]["all_moves_set_velocities_before_move"] is True
    assert report["moves_dispatched"] == report["recording"]["moves"]
    assert report["moves_dispatched"] > 0
    # Every recorded command carries a full 7-vector (not per-joint host_monitor).
    for move in arm.moves:
        assert move["joint_count"] == 7
        assert move["single_joint"] is False
        assert len(move["q_rad"]) == 7
        assert len(move["joint_velocity_limits_rad_s"]) == 7
        assert move["post_move_sleep"] is False
        assert move["max_tcp_speed_m_s"] == pytest.approx(0.02)
        assert move["planned_duration_s"] >= 0.01 - 1e-12
    assert len(report["segment_end_errors_m"]) == 3
    for seg in report["segment_end_errors_m"]:
        assert seg["error_m"] <= 0.01 + 1e-9
    assert report["j2_min_rad_observed"] >= -0.07 - 1e-12


def test_plan_step_velocity_limits_match_tcp_budget():
    tip0 = [0.0, 0.0, 0.0]
    tip1 = [0.02, 0.0, 0.0]  # 20 mm chord → ≥1.0 s at 0.02 m/s
    q0 = [0.0] * 7
    q1 = [0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    T, vels, accs = plan_step_velocity_limits(
        q0, q1, tip0, tip1, max_tcp_speed_m_s=0.02
    )
    assert T == pytest.approx(1.0)
    assert vels[0] == pytest.approx(0.1)
    assert all(a == pytest.approx(50.0) for a in accs)


def test_static_validation_preserves_j2_floor(path_doc):
    static = validate_path_static(
        path_doc,
        path_file=PATH_215245,
        expected_sha256_lf=EXPECTED_LF,
        urdf_path=URDF,
    )
    assert static["ok"] is True
    assert static["j2_min_rad"] >= -0.07 - 1e-12
    assert static["grasp_ready_tip_m"][0] == pytest.approx(0.43704060430410385, abs=1e-9)
