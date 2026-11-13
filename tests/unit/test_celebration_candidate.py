from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "config" / "motions" / "celebrate_external_candidate.yaml"


def test_external_celebration_candidate_is_attributed_and_default_closed() -> None:
    data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))

    assert data["status"] == "asymmetric_loop_hardware_validated_default_closed"
    assert data["live_motion_enabled"] is False
    assert data["arm_motion_source"]["source_gesture"] == "celebrate"
    assert data["arm_motion_source"]["license"] == "Apache-2.0"
    assert data["hand_pose_source"]["preset"] == "v_sign"
    assert data["hand_pose_source"]["license"] == "MIT"
    assert data["hand_pose_source"]["raw_u8"] == [60, 140, 255, 255, 0, 0]
    assert data["retarget_target"]["joint_mapping"]["left"]["hero_lift"] == "J2"
    assert data["retarget_target"]["joint_mapping"]["right"]["fist_pump"] == "J4"
    assert data["implemented_motion"]["loop_count"]["maximum"] == 10
    assert data["implemented_motion"]["loop_boundary"] == "same_asymmetric_anchor"
    validation = data["retarget_target"]["hardware_validation"]
    assert validation["verdict"] == "PASS"
    assert validation["loops_requested"] == validation["loops_completed"] == 5
    assert validation["left_return_max_error_rad"] < validation["return_tolerance_rad"]
    assert validation["right_return_max_error_rad"] < validation["return_tolerance_rad"]
    assert validation["can2_error_count"] == validation["can3_error_count"] == 0
    assert data["safety"]["permit_live_execution"] is False
