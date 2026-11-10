"""Classify ArmState for host readiness: recorded vs live VALID.

Live formal grasp requires source=real and validity=VALID with seven finite
joint angles (M-7). ArmStateReader today always leaves J6/J7 None and marks
INVALID (no audited read-only position query). Recorded bindings fill
device_id only and never count as live VALID. MockArm is VALID but mock-only.

This module never opens CAN, never enables motion, and never raises
control_ready. Optional live reads go through ArmStateReader separately.
"""
from __future__ import annotations

import math
from typing import Any
from uuid import uuid4

from brick_stacking.arm.state import ENDPOINTS, JOINTS
from brick_stacking.contracts import ArmState, JointName, Source, Validity

LIVE_OR_RECORDED_SCHEMA = "arm-live-or-recorded-0.1"
CLASSIFICATION_SCHEMA = "arm-state-validity-classification-0.1"

# Conditions for counts_as_live_valid (formal / SafetyGate live feedback).
LIVE_VALID_CONDITIONS = (
    "source_is_real",
    "validity_field_is_VALID",
    "device_id_present",
    "joint_names_j1_through_j7",
    "all_seven_q_rad_finite",
    "fault_is_none",
    "clock_domain_host_monotonic",
    "epoch_present",
    "host_receive_stamp_finite",
)

# Why ArmStateReader samples stay INVALID today (audited readonly path).
ARM_STATE_READER_LIVE_HOLD = (
    "J6/J7: no audited read-only position query (ArmStateReader leaves q_rad None)",
    "validity remains INVALID until seven finite joint angles are available",
    "Rest/raw V2 capture is not an audited read-only path and is not used here",
)


def unwrap_arm_state(payload: dict[str, Any] | ArmState | None) -> ArmState | None:
    """Accept raw ArmState or recorded/live wrapper with nested arm_state."""
    if payload is None:
        return None
    if not isinstance(payload, dict):
        return None
    if (
        payload.get("schema_version")
        in {LIVE_OR_RECORDED_SCHEMA, "recorded-arm-state-0.1"}
        and isinstance(payload.get("arm_state"), dict)
    ):
        return payload["arm_state"]  # type: ignore[return-value]
    if "device_id" in payload and "source" in payload and "validity" in payload:
        return payload  # type: ignore[return-value]
    if isinstance(payload.get("arm_state"), dict):
        return payload["arm_state"]  # type: ignore[return-value]
    return None


def _finite(value: Any) -> bool:
    try:
        return type(value) in (float, int) and math.isfinite(float(value))
    except (TypeError, OverflowError, ValueError):
        return False


def joint_completeness(state: ArmState | dict[str, Any]) -> dict[str, Any]:
    names = tuple(state.get("joint_names") or ())
    q = tuple(state.get("q_rad") or ())
    present: list[str] = []
    missing: list[str] = []
    for index, joint in enumerate(JOINTS):
        if index < len(q) and _finite(q[index]):
            present.append(joint)
        else:
            missing.append(joint)
    return {
        "expected_joint_names": list(JOINTS),
        "joint_names_ok": names == JOINTS,
        "finite_joints": present,
        "missing_or_nonfinite_joints": missing,
        "all_seven_finite": len(missing) == 0 and len(q) == len(JOINTS),
    }


def classify_arm_state(state: ArmState | dict[str, Any] | None) -> dict[str, Any]:
    """Machine-readable validity classification; never elevates control_ready."""
    if state is None:
        return {
            "schema_version": CLASSIFICATION_SCHEMA,
            "present": False,
            "source": None,
            "device_id": None,
            "validity": None,
            "reason": "arm_state missing",
            "source_kind": "missing",
            "device_id_ok": False,
            "counts_as_recorded_binding": False,
            "counts_as_mock_valid": False,
            "counts_as_live_valid": False,
            "condition_status": {name: "MISSING" for name in LIVE_VALID_CONDITIONS},
            "blockers": ["arm_state missing"],
            "joint_completeness": None,
            "arm_state_reader_live_hold": list(ARM_STATE_READER_LIVE_HOLD),
            "control_ready": False,
            "motion_enabled": False,
        }

    source = state.get("source")
    validity = state.get("validity")
    device_id = state.get("device_id")
    joints = joint_completeness(state)
    reason = state.get("reason")

    condition_status = {
        "source_is_real": "PASS" if source == "real" else "FAIL",
        "validity_field_is_VALID": "PASS" if validity == "VALID" else "FAIL",
        "device_id_present": "PASS" if device_id else "FAIL",
        "joint_names_j1_through_j7": "PASS" if joints["joint_names_ok"] else "FAIL",
        "all_seven_q_rad_finite": "PASS" if joints["all_seven_finite"] else "FAIL",
        "fault_is_none": "PASS" if state.get("fault") is None else "FAIL",
        "clock_domain_host_monotonic": (
            "PASS" if state.get("clock_domain") == "host_monotonic" else "FAIL"
        ),
        "epoch_present": "PASS" if state.get("epoch") else "FAIL",
        "host_receive_stamp_finite": (
            "PASS" if _finite(state.get("host_receive_stamp")) else "FAIL"
        ),
    }
    blockers = [
        name for name, status in condition_status.items() if status != "PASS"
    ]
    structural_ok = all(
        condition_status[name] == "PASS"
        for name in LIVE_VALID_CONDITIONS
        if name != "source_is_real"
    ) and validity == "VALID"
    counts_as_live_valid = not blockers and source == "real" and structural_ok
    counts_as_mock_valid = source == "mock" and structural_ok
    counts_as_recorded_binding = source == "recorded" and bool(device_id)

    if source == "recorded":
        source_kind = "recorded"
    elif source == "mock":
        source_kind = "mock"
    elif source == "real":
        source_kind = "live_real"
    else:
        source_kind = "unknown"

    return {
        "schema_version": CLASSIFICATION_SCHEMA,
        "present": True,
        "source": source,
        "device_id": device_id,
        "validity": validity,
        "reason": reason,
        "source_kind": source_kind,
        "device_id_ok": bool(device_id),
        "counts_as_recorded_binding": counts_as_recorded_binding,
        "counts_as_mock_valid": counts_as_mock_valid,
        "counts_as_live_valid": counts_as_live_valid,
        "condition_status": condition_status,
        "blockers": blockers,
        "joint_completeness": joints,
        "arm_state_reader_live_hold": list(ARM_STATE_READER_LIVE_HOLD),
        "notes": [
            "recorded/mock VALID (or recorded binding) do not count as live VALID.",
            "ArmStateReader readonly path currently cannot satisfy all_seven_q_rad_finite.",
            "This classifier never raises control_ready or opens CAN.",
        ],
        "control_ready": False,
        "motion_enabled": False,
    }


def assign_validity_from_joints(
    *,
    positions: list[float | None] | tuple[float | None, ...],
    failures: list[str],
) -> tuple[Validity, str | None]:
    """Shared rule used by readers: any missing joint or failure → INVALID."""
    missing = [
        JOINTS[i]
        for i, value in enumerate(positions)
        if i < len(JOINTS) and not _finite(value)
    ]
    if len(positions) < len(JOINTS):
        missing.extend(JOINTS[len(positions) :])
    reasons = list(failures)
    if missing:
        reasons.append("missing_or_nonfinite:" + ",".join(missing))
    if reasons or missing:
        return "INVALID", "; ".join(reasons)
    return "VALID", None


def build_fixture_valid_arm_state(
    *,
    role: str = "left",
    source: Source = "recorded",
    q_rad: tuple[float, ...] | None = None,
    host_receive_stamp: float = 1.0,
    epoch: str | None = None,
    device_id: str | None = None,
) -> ArmState:
    """Build a structurally VALID ArmState for Mock/recorded path tests.

    Never opens CAN. source=recorded|mock only — refuse source=real so fixtures
    cannot impersonate a live ArmStateReader sample.
    """
    if source == "real":
        raise ValueError(
            "fixture builder refuses source=real; use ArmStateReader for live samples"
        )
    if role not in ENDPOINTS:
        raise ValueError("role must be left or right")
    channel, _usb, ids = ENDPOINTS[role]
    joints: tuple[float, ...]
    if q_rad is None:
        joints = tuple(0.01 * (i + 1) for i in range(len(JOINTS)))
    else:
        if len(q_rad) != len(JOINTS) or not all(_finite(v) for v in q_rad):
            raise ValueError("q_rad requires seven finite joint positions")
        joints = tuple(float(v) for v in q_rad)
    resolved_id = device_id or f"{channel}:{','.join(map(str, ids))}"
    validity, reason = assign_validity_from_joints(positions=list(joints), failures=[])
    joint_names: tuple[JointName, ...] = JOINTS
    return {
        "sample_id": uuid4().hex,
        "source": source,
        "device_id": resolved_id,
        "frame_id": f"{role}_arm_base",
        "device_stamp": None,
        "host_receive_stamp": float(host_receive_stamp),
        "clock_domain": "host_monotonic",
        "epoch": epoch or f"fixture-valid/{role}/{resolved_id}",
        "validity": validity,
        "reason": reason,
        "joint_names": joint_names,
        "joint_bindings": {
            joint: {"sdk_index": index, "device_joint_id": str(motor_id)}
            for index, (joint, motor_id) in enumerate(zip(joint_names, ids, strict=True))
        },
        "q_rad": joints,
        "dq_rad_s": None,
        "enabled": False,
        "fault": None,
    }


def emit_live_or_recorded_payload(
    *,
    mode: str,
    arm_state: ArmState,
    classification: dict[str, Any] | None = None,
    binding_path: str | None = None,
    can_opened: bool = False,
    fresh_live_read: bool = False,
    extra_notes: list[str] | None = None,
) -> dict[str, Any]:
    """Unified machine-readable envelope for readiness consumers."""
    classified = classification or classify_arm_state(arm_state)
    notes = [
        "Host checklist accepts recorded/mock for arm_state_device_id only.",
        "live_valid_arm_state requires source=real + validity=VALID + seven finite q_rad.",
        "Never raises control_ready; never enables motion.",
    ]
    if extra_notes:
        notes.extend(extra_notes)
    return {
        "schema_version": LIVE_OR_RECORDED_SCHEMA,
        "kind": "arm_live_or_recorded",
        "mode": mode,
        "binding_path": binding_path,
        "arm_state": arm_state,
        "device_id": arm_state.get("device_id"),
        "source": arm_state.get("source"),
        "validity": arm_state.get("validity"),
        "fresh_live_read": bool(fresh_live_read),
        "can_opened": bool(can_opened),
        "motion_enabled": False,
        "control_ready": False,
        "classification": classified,
        "counts_as_live_valid": classified.get("counts_as_live_valid") is True,
        "counts_as_recorded_binding": classified.get("counts_as_recorded_binding") is True,
        "notes": notes,
    }


def try_live_readonly_arm_state(
    *,
    role: str = "left",
    channel: str | None = None,
) -> dict[str, Any]:
    """Best-effort ArmStateReader open+read; never enables motion.

    On non-Linux / missing python-can / binding failure, returns a soft report
    without raising control_ready. Does not send Rest or any motion command.
    """
    from brick_stacking.arm.state import ArmStateReader

    expected_channel, _path, _ids = ENDPOINTS[role]
    use_channel = channel or expected_channel
    report: dict[str, Any] = {
        "schema_version": LIVE_OR_RECORDED_SCHEMA,
        "kind": "arm_live_readonly_attempt",
        "mode": "live_readonly",
        "role": role,
        "channel": use_channel,
        "attempted": True,
        "fresh_live_read": False,
        "can_opened": False,
        "motion_enabled": False,
        "control_ready": False,
        "arm_state": None,
        "classification": None,
        "error": None,
        "arm_state_reader_live_hold": list(ARM_STATE_READER_LIVE_HOLD),
    }
    try:
        with ArmStateReader.open(role, use_channel) as reader:
            report["can_opened"] = True
            state = reader.read_state()
            report["arm_state"] = state
            report["fresh_live_read"] = True
            report["classification"] = classify_arm_state(state)
            report["device_id"] = state.get("device_id")
            report["source"] = state.get("source")
            report["validity"] = state.get("validity")
            report["counts_as_live_valid"] = (
                report["classification"].get("counts_as_live_valid") is True
            )
    except Exception as exc:  # noqa: BLE001 — soft probe for readiness tooling
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["classification"] = classify_arm_state(None)
        report["counts_as_live_valid"] = False
    report["control_ready"] = False
    report["motion_enabled"] = False
    return report
