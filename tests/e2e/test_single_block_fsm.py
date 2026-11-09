from dataclasses import replace
from pathlib import Path

import pytest

from brick_stacking.execution.pick_place_fsm import PickPlaceFSM
from brick_stacking.execution.safety_gate import StepEvidence
from brick_stacking.hardware.mock_task_world import MockTaskWorld
from brick_stacking.models.scene_state import SceneBlock, Slot, SlotState
from brick_stacking.models.task_state import TaskStage
from brick_stacking.runtime.config_loader import load_config
from brick_stacking.scene.scene_manager import SceneManager


DEVICE = "single-block-fixture"
CALIBRATION = "synthetic-calibration-v1"
CONFIG = Path(__file__).resolve().parents[2] / "config/offline_task.yaml"


@pytest.fixture
def scenario():
    def build(*, failed_grasps=0, placement_error=0., verification_for=None,
              change_evidence=lambda evidence, request: evidence):
        config = load_config(CONFIG)
        frame = config["scene"]["frame_id"]
        slot = Slot("slot-1", 0, "red", (0., 0., .025), frame, ())
        block = SceneBlock("block-1", "red", (.5, .4, .025), frame)
        manager = SceneManager((slot,))
        world = MockTaskWorld(
            (block,), tick_s=config["task"]["synthetic_tick_s"],
            fail_first_grasps=failed_grasps, placement_error_m=placement_error,
        )
        events = []
        clock = [0.]

        def evidence_for(request):
            trajectory = f"fixture:{request.stage}:{request.block_id}:{request.slot_id}"
            joints = ("J1", "J2", "J3", "J4", "J5", "J6", "J7")
            feedback = {
                "sample_id": f"{request.scene_version}:{request.stage}",
                "source": "mock", "device_id": DEVICE, "frame_id": frame,
                "device_stamp": None, "host_receive_stamp": world.now_s,
                "clock_domain": world.clock_domain, "epoch": world.epoch,
                "validity": "VALID", "reason": None, "joint_names": joints,
                "joint_bindings": {name: {"sdk_index": i, "device_joint_id": str(i + 1)}
                                   for i, name in enumerate(joints)},
                "q_rad": (0.,) * 7, "dq_rad_s": None, "enabled": None, "fault": None,
            }
            permit = {
                "device_id": DEVICE, "trajectory_hash": trajectory,
                "config_hash": request.config_hash, "calibration_hash": CALIBRATION,
                "scene_version": request.scene_version,
                "valid_until_host_monotonic_s": world.now_s + .25,
            }
            return change_evidence(StepEvidence(feedback, True, trajectory, permit), request)

        fsm = PickPlaceFSM(
            config=config, scene_manager=manager, port=world,
            event_sink=lambda name, details: events.append((name, details)),
            evidence_for=evidence_for, device_id=DEVICE, calibration_hash=CALIBRATION,
            timeout_s=1., clock=lambda: clock[0], verification_for=verification_for,
        )
        return fsm, world, manager, events, clock

    return build


@pytest.mark.parametrize("failed_grasps", [0, 1])
def test_single_block_verifies_pick_and_place(scenario, failed_grasps):
    fsm, world, manager, events, _ = scenario(failed_grasps=failed_grasps)
    result = fsm.run()
    assert result.stage == TaskStage.DONE
    assert result.verified_slots == ("slot-1",)
    assert result.recovery_attempts == failed_grasps
    assert manager.states["slot-1"] == SlotState.PLACED_VERIFIED
    assert world.payload is None
    stages = [details["stage"] for name, details in events if name == "stage"]
    assert stages.index("VERIFY_PICK") < stages.index("TRANSPORT")
    assert stages.index("VERIFY_PLACE") < stages.index("DONE")
    assert stages.count("REOBSERVE") == failed_grasps
    assert sum(name == "step_dispatched" for name, _ in events) == len(world.events)
    with pytest.raises(RuntimeError, match="single use"):
        fsm.run()


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (lambda e: replace(e, feedback={**e.feedback, "host_receive_stamp": -1.}), "stale/future"),
        (lambda e: replace(e, calibration_valid=False), "calibration"),
        (lambda e: replace(e, calibration_valid=None), "calibration"),
        (lambda e: replace(e, permit=None), "permit is unknown"),
        (lambda e: replace(e, permit={**e.permit, "valid_until_host_monotonic_s": 0.}), "expired"),
        (lambda e: replace(e, permit={**e.permit, "valid_until_host_monotonic_s": 100.}), "freshness window"),
        (lambda e: replace(e, permit={**e.permit, "trajectory_hash": "other"}), "step context"),
        (lambda e: replace(e, permit={**e.permit, "scene_version": "old"}), "step context"),
    ],
)
def test_gate_refuses_before_dispatch(scenario, change, reason):
    fsm, world, manager, events, _ = scenario(change_evidence=lambda e, _: change(e))
    result = fsm.run()
    assert result.stage == TaskStage.SAFE_HALT and reason in result.reason
    assert not manager.occupants
    assert [event["stage"] for event in world.events] == ["MOCK_STOP"]
    assert events[-1][1]["reason"] == result.reason


def test_gate_rechecks_permit_after_pick(scenario):
    def revoke_on_transport(evidence, request):
        return replace(evidence, permit=None) if request.stage == "TRANSPORT" else evidence

    fsm, world, manager, _, _ = scenario(change_evidence=revoke_on_transport)
    assert fsm.run().stage == TaskStage.SAFE_HALT
    assert [event["stage"] for event in world.events] == ["PRE_GRASP", "GRASP", "MOCK_STOP"]
    assert world.payload == "block-1" and not manager.occupants


def test_deadline_expiring_during_evidence_read_blocks_dispatch(scenario):
    def slow_evidence(evidence, request):
        clock[0] = 1.
        return evidence

    fsm, world, manager, _, clock = scenario(change_evidence=slow_evidence)
    result = fsm.run()
    assert result.stage == TaskStage.SAFE_HALT and "deadline exceeded" in result.reason
    assert not manager.occupants
    assert [event["stage"] for event in world.events] == ["MOCK_STOP"]


def test_grasp_exhaustion_is_bounded(scenario):
    fsm, world, manager, _, _ = scenario(failed_grasps=10)
    result = fsm.run()
    assert result.stage == TaskStage.SAFE_HALT and result.recovery_attempts == 2
    assert sum(event["stage"] == "GRASP" for event in world.events) == 3
    assert not manager.occupants


def test_bad_placement_is_not_committed(scenario):
    fsm, world, manager, _, _ = scenario(placement_error=.1)
    assert fsm.run().stage == TaskStage.SAFE_HALT
    assert manager.states["slot-1"] == SlotState.UNVERIFIED
    assert not manager.occupants and world.events[-1]["stage"] == "MOCK_STOP"


def visual_fixture(*, phase, block_id, slot, before, after, scene_version, config_hash, calibration_hash):
    assert slot.slot_id == "slot-1"
    refs = (before.observation_id, after.observation_id)
    return {
        "sample_id": f"visual:{phase}:{after.observation_id}", "source": "mock",
        "device_id": "mock-camera", "frame_id": "mock-camera-optical", "device_stamp": None,
        "object_id": block_id, "phase": phase, "validity": "VALID", "verdict": "PASS",
        "reason": None, "error_m": None, "clock_domain": after.clock_domain, "epoch": after.epoch,
        "host_receive_stamp": after.stamp_s, "scene_version": scene_version,
        "config_hash": config_hash, "calibration_hash": calibration_hash,
        "observation_refs": refs, "image_refs": tuple(f"mock-image:{ref}" for ref in refs),
        "scope": "held" if phase == "PICK" else "released_stable",
    }


def test_consumes_pick_and_place_evidence(scenario):
    fsm, _, manager, events, _ = scenario(verification_for=visual_fixture)
    assert fsm.run().stage == TaskStage.DONE
    assert manager.states["slot-1"] == SlotState.PLACED_VERIFIED
    assert [row["phase"] for name, row in events if name == "visual_verification"] == ["PICK", "PLACE"]


@pytest.mark.parametrize(("phase", "override", "reason"), [
    ("PICK", {"verdict": "FAIL"}, "not verified"),
    ("PICK", {"verdict": "UNKNOWN", "reason": "occluded"}, "not verified"),
    ("PICK", {"host_receive_stamp": -1.}, "stale/future"),
    ("PICK", {"observation_refs": ("old-before", "old-after")}, "context mismatch"),
    ("PLACE", {"calibration_hash": "changed-camera-geometry"}, "context mismatch"),
    ("PLACE", {"scope": "position_only"}, "scope or provenance insufficient"),
])
def test_visual_evidence_cannot_advance_transaction(scenario, phase, override, reason):
    def verification_for(**request):
        result = visual_fixture(**request)
        return {**result, **override} if request["phase"] == phase else result

    fsm, world, manager, _, _ = scenario(verification_for=verification_for)
    result = fsm.run()
    assert result.stage == TaskStage.SAFE_HALT and reason in result.reason
    assert not manager.occupants
    if phase == "PICK":
        assert [event["stage"] for event in world.events] == ["PRE_GRASP", "GRASP", "MOCK_STOP"]
    else:
        assert manager.states["slot-1"] == SlotState.UNVERIFIED
