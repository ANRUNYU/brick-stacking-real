"""Mock-only single-block pick→place replay against a PlanBundle.

Accepts only MockArm with hardware_enabled=False. Uses in-memory hand presets
(MOCK_OPEN / MOCK_HOLD). Never opens O6 or sends CAN. Visual recheck is mock
evidence (source=mock); no PASS → no slot commit.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

from brick_stacking.arm.adapter import JOINT_NAMES, MockArm, trajectory_hash, validate_trajectory
from brick_stacking.hardware.mock_devices import MockHand
from brick_stacking.models.scene_state import SceneBlock, Slot, SlotState
from brick_stacking.scene.scene_manager import SceneManager


class ReplayStage(str, Enum):
    PRE_GRASP = "PRE_GRASP"
    GRASP = "GRASP"
    VERIFY_PICK = "VERIFY_PICK"
    TRANSPORT = "TRANSPORT"
    PLACE = "PLACE"
    RETREAT = "RETREAT"
    VERIFY_PLACE = "VERIFY_PLACE"
    DONE = "DONE"
    SAFE_HALT = "SAFE_HALT"


STAGE_ORDER = (
    ReplayStage.PRE_GRASP,
    ReplayStage.GRASP,
    ReplayStage.VERIFY_PICK,
    ReplayStage.TRANSPORT,
    ReplayStage.PLACE,
    ReplayStage.RETREAT,
    ReplayStage.VERIFY_PLACE,
    ReplayStage.DONE,
)


@dataclass
class ReplayResult:
    stage: ReplayStage
    reason: str | None = None
    stages: list[str] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    slot_state: SlotState | None = None
    hand_preset: str | None = None
    payload: str | None = None
    trajectory_hash: str | None = None


class _Clock:
    def __init__(self, t0: float = 0.0):
        self.t = float(t0)

    def __call__(self) -> float:
        return self.t

    def advance_to(self, t: float) -> None:
        if t < self.t:
            raise ValueError("clock went backwards")
        self.t = float(t)


def _require_mock_arm(arm: Any) -> MockArm:
    if not isinstance(arm, MockArm):
        raise ValueError("single-block mock replay rejects non-MockArm port")
    if getattr(arm, "backend", None) != "mock":
        raise ValueError("single-block mock replay rejects non-mock backend")
    if getattr(arm, "hardware_enabled", None) is not False:
        raise ValueError("single-block mock replay requires hardware_enabled=False")
    return arm


def _bundle_contract_trajectory(bundle: dict[str, Any]) -> dict[str, Any]:
    traj = bundle.get("trajectory")
    if not traj or not traj.get("points"):
        raise ValueError("PlanBundle missing trajectory points")
    full = validate_trajectory({
        "joint_names": traj["joint_names"],
        "points": tuple(
            {"time_from_start_s": p["time_from_start_s"], "q_rad": tuple(p["q_rad"])}
            for p in traj["points"]
        ),
    })


    digest = trajectory_hash(full)
    if digest != bundle.get("trajectory_hash") or digest != traj.get("hash"):
        raise ValueError("single-block trajectory hash mismatch")
    return full


def _phase_point_index(bundle: dict[str, Any], phase: str) -> int:
    idx = (bundle.get("phase_index") or {}).get(phase)
    if idx is None:
        raise ValueError(f"PlanBundle missing phase_index for {phase}")
    # trajectory points: [seed=0] + waypoint solutions; waypoint i → point i+1
    return int(idx) + 1


def _sub_trajectory(full: dict[str, Any], end_index: int, *, start_index: int = 0) -> dict[str, Any]:
    points = list(full["points"])
    if not 0 <= start_index < end_index < len(points):
        raise ValueError("invalid trajectory slice")
    base_t = points[start_index]["time_from_start_s"]
    sliced = [
        {
            "time_from_start_s": float(p["time_from_start_s"] - base_t),
            "q_rad": p["q_rad"],
        }
        for p in points[start_index : end_index + 1]
    ]
    for i in range(1, len(sliced)):
        if sliced[i]["time_from_start_s"] <= sliced[i - 1]["time_from_start_s"]:
            sliced[i]["time_from_start_s"] = sliced[i - 1]["time_from_start_s"] + 1e-3
    return validate_trajectory({"joint_names": full["joint_names"], "points": tuple(sliced)})


def _drive_segment(arm: MockArm, clock: _Clock, trajectory: dict[str, Any]) -> None:
    last_t = trajectory["points"][-1]["time_from_start_s"]
    permit = {
        "device_id": arm._context[0],  # noqa: SLF001
        "config_hash": arm._context[1],  # noqa: SLF001
        "calibration_hash": arm._context[2],  # noqa: SLF001
        "scene_version": arm._context[3],  # noqa: SLF001
        "trajectory_hash": trajectory_hash(trajectory),
        "valid_until_host_monotonic_s": clock() + last_t + 30.0,
    }
    command_id = arm.execute_trajectory(trajectory, permit)
    started = arm.get_execution_result(command_id)["started_host_monotonic_s"]
    for point in trajectory["points"]:
        clock.advance_to(started + point["time_from_start_s"] + 1e-6)
        arm.step(command_id)
    status = arm.get_execution_status(command_id)
    if status != "SUCCEEDED":
        clock.advance_to(started + last_t + 0.02)
        arm.step(command_id)
        status = arm.get_execution_status(command_id)
    if status != "SUCCEEDED":
        result = arm.get_execution_result(command_id)
        raise RuntimeError(f"mock arm segment failed: {status} {result.get('reason')}")


def mock_visual_evidence(
    *,
    phase: str,
    block_id: str,
    scene_version: str,
    config_hash: str,
    calibration_hash: str,
    stamp_s: float,
    verdict: str = "PASS",
) -> dict[str, Any]:
    scope = "held" if phase == "PICK" else "released_stable"
    return {
        "object_id": block_id,
        "phase": phase,
        "scene_version": scene_version,
        "config_hash": config_hash,
        "calibration_hash": calibration_hash,
        "clock_domain": "host_monotonic",
        "epoch": "mock-replay",
        "host_receive_stamp": stamp_s,
        "observation_refs": (f"before-{phase}", f"after-{phase}"),
        "validity": "VALID" if verdict == "PASS" else "INVALID",
        "verdict": verdict,
        "scope": scope,
        "sample_id": f"mock-vis-{phase}-{uuid4().hex[:8]}",
        "image_refs": [f"mock://{phase}/a.png", f"mock://{phase}/b.png"],
        "source": "mock",
    }


def make_mock_arm_for_bundle(bundle: dict[str, Any], clock: _Clock | None = None) -> tuple[MockArm, _Clock]:
    """Construct MockArm seeded to PlanBundle start, bound to a shared clock."""
    clock = clock or _Clock(0.0)
    traj = _bundle_contract_trajectory(bundle)
    seed = traj["points"][0]["q_rad"]
    identity = bundle.get("identity") or {}
    arm = MockArm(
        seed,
        clock=clock,
        device_id="mock-arm-single-block",
        config_hash=str(identity.get("config_hash") or "mock-config"),
        calibration_hash=str(identity.get("calibration_hash") or "mock-calibration"),
        scene_version=str(identity.get("scene_version") or "mock-scene"),
    )
    return arm, clock


def run_single_block_mock_replay(
    bundle: dict[str, Any],
    *,
    arm: Any | None = None,
    clock: _Clock | None = None,
    hand: MockHand | None = None,
    block_id: str = "block-1",
    slot_id: str | None = None,
    place_center_m: Sequence[float] | None = None,
    pick_center_m: Sequence[float] | None = None,
    frame_id: str | None = None,
    placement_tolerance_m: float = 0.015,
    visual_verdict_pick: str = "PASS",
    visual_verdict_place: str = "PASS",
) -> ReplayResult:
    """Replay PlanBundle stages on MockArm; commit slot only after mock PASS."""
    events: list[dict[str, Any]] = []
    stages: list[str] = []
    hand = hand or MockHand(role="left")

    def halt(reason: str) -> ReplayResult:
        stages.append(ReplayStage.SAFE_HALT.value)
        events.append({"kind": "SAFE_HALT", "reason": reason})
        return ReplayResult(
            stage=ReplayStage.SAFE_HALT, reason=reason, stages=stages, events=events,
            hand_preset=hand.get_state()["preset"],
            trajectory_hash=bundle.get("trajectory_hash"),
        )

    if arm is None:
        if bundle.get("trajectory_hash") and bundle.get("trajectory"):
            try:
                arm, clock = make_mock_arm_for_bundle(bundle, clock)
            except ValueError as exc:
                return halt(str(exc))
        else:
            return halt(bundle.get("reason") or "PlanBundle not dispatchable")
    else:
        try:
            arm = _require_mock_arm(arm)
        except ValueError as exc:
            return halt(str(exc))
        clock = clock or _Clock(0.0)

    if bundle.get("schema_version") != "m-single-block-plan-bundle-0.1":
        return halt("unsupported PlanBundle schema")
    if bundle.get("executable") is not False:
        return halt("refusing executable=true package on mock software path")
    if bundle.get("motion_enabled") is not False:
        return halt("refusing motion_enabled=true package on mock software path")
    if bundle.get("status") == "SAFE_HALT" or not bundle.get("trajectory_hash"):
        return halt(bundle.get("reason") or "PlanBundle not dispatchable")
    if bundle.get("collision_summary", {}).get("table_clearance") != "PASS":
        return halt("table clearance not PASS; refusing dispatch")
    if any(bundle.get(key) is not False for key in ("control_ready", "dispatch_allowed", "h3_production_plan")):
        return halt("unexpected authority flags in mock bundle")
    if bundle.get("collision_summary", {}).get("full_collision") != "UNKNOWN":
        return halt("unexpected full_collision verdict in mock bundle")

    identity = bundle["identity"]
    poses = bundle["poses"]
    if (slot_id is not None and slot_id != identity["slot_id"]
            or frame_id is not None and frame_id != poses["frame"]
            or identity["frame_id"] != poses["frame"]
            or place_center_m is not None and tuple(place_center_m) != tuple(poses["place_center_m"])
            or pick_center_m is not None and tuple(pick_center_m) != tuple(poses["pick_center_m"])):
        return halt("replay context differs from plan")
    slot_id = identity["slot_id"]
    frame_id = poses["frame"]
    place_center_m = poses["place_center_m"]
    pick_center_m = poses["pick_center_m"]
    slot = Slot(slot_id, 0, "red", tuple(place_center_m), frame_id, ())
    _block = SceneBlock(block_id, "red", tuple(pick_center_m), frame_id)
    manager = SceneManager((slot,))
    payload: str | None = None

    try:
        full = _bundle_contract_trajectory(bundle)
    except ValueError as exc:
        return halt(str(exc))

    def drive_to_phase(phase: str, *, from_phase: str | None = None) -> None:
        end_i = _phase_point_index(bundle, phase)
        start_i = 0 if from_phase is None else _phase_point_index(bundle, from_phase)
        traj = _sub_trajectory(full, end_i, start_index=start_i)
        _drive_segment(arm, clock, traj)

    try:
        stages.append(ReplayStage.PRE_GRASP.value)
        hand.simulate_preset("MOCK_OPEN")
        events.append({"stage": "PRE_GRASP", "hand": "MOCK_OPEN", "physical_execution": False})
        drive_to_phase("pick_above")

        stages.append(ReplayStage.GRASP.value)
        drive_to_phase("grasp_close", from_phase="pick_above")
        hand.simulate_preset("MOCK_HOLD")
        payload = block_id
        events.append({"stage": "GRASP", "hand": "MOCK_HOLD", "payload": payload, "physical_execution": False})

        stages.append(ReplayStage.VERIFY_PICK.value)
        identity = bundle.get("identity") or {}
        evidence = mock_visual_evidence(
            phase="PICK", block_id=block_id,
            scene_version=str(identity.get("scene_version") or "scene"),
            config_hash=str(identity.get("config_hash") or "cfg"),
            calibration_hash=str(identity.get("calibration_hash") or "cal"),
            stamp_s=clock(),
            verdict=visual_verdict_pick,
        )
        events.append({"stage": "VERIFY_PICK", "evidence": evidence})
        if evidence["verdict"] != "PASS" or evidence.get("source") != "mock":
            return halt("VERIFY_PICK mock evidence not PASS")
        drive_to_phase("pick_lift", from_phase="grasp_close")

        stages.append(ReplayStage.TRANSPORT.value)
        drive_to_phase("place_above", from_phase="pick_lift")
        events.append({"stage": "TRANSPORT", "payload": payload, "physical_execution": False})

        stages.append(ReplayStage.PLACE.value)
        drive_to_phase("place_open", from_phase="place_above")
        hand.simulate_preset("MOCK_OPEN")
        placed = list(place_center_m)
        placement_err = (
            (float(placed[0]) - float(place_center_m[0])) ** 2
            + (float(placed[1]) - float(place_center_m[1])) ** 2
        ) ** 0.5
        if placement_err > placement_tolerance_m:
            return halt(f"placement error {placement_err} exceeds tolerance")
        payload = None
        events.append({"stage": "PLACE", "hand": "MOCK_OPEN", "placed_m": placed, "physical_execution": False})

        stages.append(ReplayStage.RETREAT.value)
        drive_to_phase("retreat_wait", from_phase="place_open")
        events.append({"stage": "RETREAT", "physical_execution": False})

        stages.append(ReplayStage.VERIFY_PLACE.value)
        evidence = mock_visual_evidence(
            phase="PLACE", block_id=block_id,
            scene_version=str(identity.get("scene_version") or "scene"),
            config_hash=str(identity.get("config_hash") or "cfg"),
            calibration_hash=str(identity.get("calibration_hash") or "cal"),
            stamp_s=clock(),
            verdict=visual_verdict_place,
        )
        events.append({"stage": "VERIFY_PLACE", "evidence": evidence})
        if evidence["verdict"] != "PASS":
            return halt("VERIFY_PLACE mock evidence not PASS")

        manager.reserve(slot.slot_id, block_id)
        manager.mark_unverified(slot.slot_id)
        manager.commit_verified(slot.slot_id, block_id)
        stages.append(ReplayStage.DONE.value)
        return ReplayResult(
            stage=ReplayStage.DONE,
            stages=stages,
            events=events,
            slot_state=manager.states[slot.slot_id],
            hand_preset=hand.get_state()["preset"],
            payload=payload,
            trajectory_hash=bundle.get("trajectory_hash"),
        )
    except Exception as exc:  # noqa: BLE001 — closed-loop maps failures to SAFE_HALT
        return halt(f"SAFE_HALT: {exc}")


# Re-export for tests that assert joint naming.
__all__ = [
    "ReplayResult",
    "ReplayStage",
    "STAGE_ORDER",
    "make_mock_arm_for_bundle",
    "mock_visual_evidence",
    "run_single_block_mock_replay",
    "JOINT_NAMES",
]
