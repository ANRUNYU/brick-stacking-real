"""Recorded arm device_id binding from audited config (no CAN).

`ArmState.device_id` format matches `ArmStateReader`:
  ``{channel}:{id1},{id2},...,{id7}``
e.g. left P7 → ``can2:61,62,63,64,65,66,67``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from brick_stacking.arm.state import ENDPOINTS, JOINTS
from brick_stacking.contracts import ArmState, JointName

SCHEMA = "arm-device-binding-0.1"
RECORDED_ARM_STATE_SCHEMA = "recorded-arm-state-0.1"


def format_arm_device_id(channel: str, motor_ids: tuple[int, ...] | list[int]) -> str:
    return f"{channel}:{','.join(map(str, motor_ids))}"


def load_arm_device_binding(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA:
        raise ValueError(f"expected {SCHEMA}, got {payload.get('schema_version')}")
    role = payload.get("role")
    if role not in ENDPOINTS:
        raise ValueError("arm binding role must be left or right")
    channel, _usb, ids = ENDPOINTS[role]
    if payload.get("channel") != channel:
        raise ValueError(f"channel mismatch for {role}: config={payload.get('channel')} code={channel}")
    cfg_ids = tuple(int(x) for x in payload["motor_ids"])
    if cfg_ids != ids:
        raise ValueError(f"motor_ids mismatch for {role}: config={cfg_ids} code={ids}")
    expected = format_arm_device_id(channel, ids)
    if payload.get("device_id") != expected:
        raise ValueError(f"device_id mismatch: config={payload.get('device_id')} expected={expected}")
    return payload


def recorded_arm_state_from_binding(
    binding: dict[str, Any],
    *,
    host_receive_stamp: float = 0.0,
    epoch: str | None = None,
) -> ArmState:
    """Build a recorded ArmState for host checklist; never opens CAN."""
    role = binding["role"]
    channel, _usb, ids = ENDPOINTS[role]
    device_id = format_arm_device_id(channel, ids)
    joint_names: tuple[JointName, ...] = JOINTS
    return {
        "sample_id": uuid4().hex,
        "source": "recorded",
        "device_id": device_id,
        "frame_id": f"{role}_arm_base",
        "device_stamp": None,
        "host_receive_stamp": float(host_receive_stamp),
        "clock_domain": "host_monotonic",
        "epoch": epoch or f"recorded-binding/{role}/{device_id}",
        "validity": "INVALID",
        "reason": (
            "recorded config/history binding only; not a live ArmStateReader sample; "
            "CAN not opened"
        ),
        "joint_names": joint_names,
        "joint_bindings": {
            joint: {"sdk_index": index, "device_joint_id": str(motor_id)}
            for index, (joint, motor_id) in enumerate(zip(joint_names, ids, strict=True))
        },
        "q_rad": tuple(None for _ in joint_names),
        "dq_rad_s": None,
        "enabled": False,
        "fault": None,
    }


def emit_recorded_arm_state_payload(
    binding: dict[str, Any],
    *,
    binding_path: str | None = None,
) -> dict[str, Any]:
    state = recorded_arm_state_from_binding(binding)
    return {
        "schema_version": RECORDED_ARM_STATE_SCHEMA,
        "kind": "recorded_arm_state",
        "binding_schema": SCHEMA,
        "binding_path": binding_path,
        "historical_label": binding.get("historical_label"),
        "evidence_refs": list(binding.get("evidence_refs") or []),
        "arm_state": state,
        "device_id": state["device_id"],
        "source": state["source"],
        "fresh_live_read": False,
        "can_opened": False,
        "motion_enabled": False,
        "control_ready": False,
        "notes": [
            "Host checklist accepts source=recorded for arm_state_device_id.",
            "Live Permit still requires a fresh ArmState matching permit.device_id.",
            "Camera SN and hand SN are never accepted as arm device_id.",
        ],
    }
