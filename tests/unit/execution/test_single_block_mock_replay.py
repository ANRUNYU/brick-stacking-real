"""Mock single-block pick/place replay e2e and negative cases."""
from pathlib import Path

from brick_stacking.arm.adapter import MockArm
from brick_stacking.execution.single_block_mock_replay import (
    ReplayStage,
    run_single_block_mock_replay,
)
from brick_stacking.models.scene_state import SlotState
from brick_stacking.planning.single_block_plan_bundle import build_single_block_plan_bundle

ROOT = Path(__file__).resolve().parents[3]
APPROACH = ROOT / "config/planning/single_block_approach.yaml"
LIMITS = ROOT / "config/planning/single_block_joint_limits_synthetic.yaml"


def _bundle(**kwargs):
    return build_single_block_plan_bundle(
        approach_config_path=APPROACH,
        limits_config_path=LIMITS,
        **kwargs,
    )


def test_mock_replay_reaches_done_and_placed_verified():
    bundle = _bundle()
    assert bundle["status"] == "PLAN_READY_NON_EXECUTABLE"
    result = run_single_block_mock_replay(bundle)
    assert result.stage == ReplayStage.DONE
    assert result.slot_state == SlotState.PLACED_VERIFIED
    assert result.payload is None
    assert result.hand_preset == "MOCK_OPEN"
    assert result.stages.index("VERIFY_PICK") < result.stages.index("TRANSPORT")
    assert result.stages.index("VERIFY_PLACE") < result.stages.index("DONE")
    assert result.stages.index("GRASP") < result.stages.index("VERIFY_PICK")


def test_reject_non_mock_port():
    bundle = _bundle()

    class FakeArm:
        backend = "hardware"
        hardware_enabled = True

    result = run_single_block_mock_replay(bundle, arm=FakeArm())
    assert result.stage == ReplayStage.SAFE_HALT
    assert "MockArm" in (result.reason or "") or "non-MockArm" in (result.reason or "")


def test_reject_executable_true_bundle():
    bundle = _bundle()
    bundle = dict(bundle)
    bundle["executable"] = True
    result = run_single_block_mock_replay(bundle)
    assert result.stage == ReplayStage.SAFE_HALT
    assert "executable" in (result.reason or "")


def test_clearance_failure_no_motion_dispatch():
    bundle = _bundle(observation_age_ok=False)
    assert bundle["status"] == "SAFE_HALT"
    result = run_single_block_mock_replay(bundle)
    assert result.stage == ReplayStage.SAFE_HALT
    assert not any(e.get("stage") == "PRE_GRASP" for e in result.events)


def test_verify_place_fail_does_not_commit():
    bundle = _bundle()
    result = run_single_block_mock_replay(bundle, visual_verdict_place="FAIL")
    assert result.stage == ReplayStage.SAFE_HALT
    assert result.slot_state is None
    assert "VERIFY_PLACE" in result.stages


def test_hardware_enabled_mock_rejected():
    bundle = _bundle()
    arm = MockArm((0.0,) * 7)
    # Tamper: simulate a non-compliant attribute (should still be False on real MockArm).
    assert arm.hardware_enabled is False
    # Non-mock object with mock-looking backend but hardware on:
    class Bad:
        backend = "mock"
        hardware_enabled = True

    result = run_single_block_mock_replay(bundle, arm=Bad())
    assert result.stage == ReplayStage.SAFE_HALT
