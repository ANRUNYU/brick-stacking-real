"""Draft M0 interface shapes, with no hardware or runtime validation."""

from __future__ import annotations

from typing import Literal, TypedDict

from brick_stacking.models.scene_state import SlotState

SCHEMA_VERSION = "0.1"

Source = Literal["mock", "recorded", "real"]
Validity = Literal["VALID", "INVALID", "UNKNOWN"]
Verdict = Literal["PASS", "FAIL", "UNKNOWN"]
ExecutionStatus = Literal[
    "PENDING", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED", "UNKNOWN"
]
HandRole = Literal["left", "right"]
JointName = Literal["J1", "J2", "J3", "J4", "J5", "J6", "J7"]
HandChannels = tuple[int, int, int, int, int, int]


class Sample(TypedDict):
    sample_id: str
    source: Source
    device_id: str
    frame_id: str
    device_stamp: float | None
    host_receive_stamp: float
    clock_domain: str
    epoch: str
    validity: Validity
    reason: str | None


class Pose(TypedDict):
    # T_parent_child maps child coordinates into the parent frame.
    parent_frame: str
    child_frame: str
    translation_m: tuple[float, float, float]
    quaternion_xyzw: tuple[float, float, float, float]


class JointBinding(TypedDict):
    sdk_index: int
    device_joint_id: str


class ArmState(Sample):
    joint_names: tuple[JointName, ...]
    joint_bindings: dict[JointName, JointBinding]
    q_rad: tuple[float, ...]
    dq_rad_s: tuple[float, ...] | None
    enabled: bool | None
    fault: str | None


class HandState(Sample):
    role: HandRole
    hand_sn: str
    raw_u8: HandChannels
    mapping_version: str
    fault_valid: bool
    temperature_valid: bool
    tactile_valid: bool


class RGBDObservation(Sample):
    camera_sn: str
    rgb_ref: str
    depth_ref: str | None
    intrinsics_k: tuple[float, ...]
    distortion_d: tuple[float, ...]
    depth_scale_m_per_unit: float
    profile: str
    depth_registered_to_rgb: bool | None
    rgb_depth_delta_s: float | None


class BlockObservation(Sample):
    observation_id: str
    camera_pose: Pose | None
    color: str
    size_m: tuple[float, float, float] | None
    size_source: str
    quality: float | None
    covariance: tuple[float, ...] | None
    visibility: str


class LocalizedBlock(Sample):
    observation_id: str
    world_pose: Pose | None
    transform_refs: tuple[str, ...]
    calibration_hash: str
    error_m: float | None


class SceneBlock(TypedDict):
    holder_id: str | None
    observation_refs: tuple[str, ...]


class SceneSlot(TypedDict):
    state: SlotState
    block_id: str | None
    support_slot_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]


class SceneSnapshot(TypedDict):
    """Versioned exchange view of task state, separate from a sensor snapshot."""

    scene_version: str
    blocks_by_id: dict[str, SceneBlock]
    slots_by_id: dict[str, SceneSlot]


class RawHandValues(TypedDict):
    unit: Literal["raw_u8"]
    values: HandChannels


class PercentHandValues(TypedDict):
    unit: Literal["percent"]
    values: tuple[float, float, float, float, float, float]


class GraspPreset(TypedDict):
    role: HandRole
    preset_version: str
    position: RawHandValues | PercentHandValues
    speed: RawHandValues | PercentHandValues
    geometry_assumptions: tuple[str, ...]
    applicable_objects: tuple[str, ...]


class PlanRequest(TypedDict):
    block_id: str
    slot_id: str
    scene_version: str
    target: Pose
    preset: GraspPreset
    start_state: ArmState
    config_hash: str


class TrajectoryPoint(TypedDict):
    time_from_start_s: float
    q_rad: tuple[float, ...]


class Trajectory(TypedDict):
    joint_names: tuple[JointName, ...]
    points: tuple[TrajectoryPoint, ...]


class PlanSegment(TypedDict):
    phase: str
    trajectory: Trajectory


class PlanResult(TypedDict):
    feasible: bool
    rejection_reason: str | None
    segments: tuple[PlanSegment, ...]
    config_hash: str
    calibration_hash: str
    collision_model_hash: str
    scene_version: str
    valid_until_host_monotonic_s: float | None


class VerificationEvidence(Sample):
    object_id: str
    phase: str
    verdict: Verdict
    error_m: float | None
    image_refs: tuple[str, ...]
    observation_refs: tuple[str, ...]


class ExecutionResult(TypedDict):
    command_id: str
    status: ExecutionStatus
    feedback: ArmState | HandState | None
    started_host_monotonic_s: float | None
    ended_host_monotonic_s: float | None
    reason: str | None


class Permit(TypedDict):
    device_id: str
    trajectory_hash: str
    config_hash: str
    calibration_hash: str
    scene_version: str
    valid_until_host_monotonic_s: float


class StopResult(TypedDict):
    request_sent: bool
    feedback_confirmed: bool
    hold_capable: bool | None
    reason: str | None
