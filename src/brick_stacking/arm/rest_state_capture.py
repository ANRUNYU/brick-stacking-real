"""Default-off Rest angle capture + dual pregrasp attest gates.

Rest (``FF×7+FD`` via ``MotorV2.read_initial_state`` / ``c_left_wrist_rest_capture``)
drops wrist holding torque. That is **not** ``--enable-motion`` / large joint
trajectory, and Goal ``不开臂/CAN`` is interpreted here as: forbid trajectory /
enable-motion; allow an **explicit, default-closed** research path that converts
an already-captured Rest sample into a live VALID *draft*.

Safety defaults (CI / default path):

* ``rest_state_capture`` defaults **false** (CLI + env).
* ``attest_rest_for_pregrasp`` defaults **false** (CLI + env) — second gate.
* Dual gate (both open) + structurally live VALID Rest draft may arm formal
  ladder via ``live_arm_via=rest_attested`` (≠ audited J6/J7 readonly).
* This module **never** opens CAN, never sends Rest, never enables motion.
* CI and default readiness paths must not auto-Rest on hardware.
* Dual gate still never raises ``control_ready`` / never enables motion.

Env:

* ``BRICK_STACKING_REST_STATE_CAPTURE`` ∈ {1,true,yes,on}
* ``BRICK_STACKING_ATTEST_REST_FOR_PREGRASP`` ∈ {1,true,yes,on}
"""
from __future__ import annotations

import math
import os
import struct
from typing import Any, Mapping
from uuid import uuid4

from brick_stacking.arm.arm_state_validity import (
    assign_validity_from_joints,
    classify_arm_state,
    emit_live_or_recorded_payload,
)
from brick_stacking.arm.state import ENDPOINTS, JOINTS
from brick_stacking.contracts import ArmState, JointName

ENV_VAR = "BRICK_STACKING_REST_STATE_CAPTURE"
ATTEST_ENV_VAR = "BRICK_STACKING_ATTEST_REST_FOR_PREGRASP"
DEFAULT_ENABLED = False
DEFAULT_ATTEST_ENABLED = False
PROVENANCE = "rest_ff7_fd_supported_capture"
DRAFT_SCHEMA = "rest-state-capture-draft-0.1"
GATE_DOC = "docs/team/B/J6J7_READONLY_POSITION_HARD_BLOCK_20261110.md"
LIVE_ARM_VIA_REST_ATTESTED = "rest_attested"


class RestStateCaptureDisabled(RuntimeError):
    """Raised when draft construction is requested while the gate is closed."""


def _env_truthy(raw: str | None) -> bool:
    if raw is None:
        return False
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def is_rest_state_capture_enabled(
    *,
    cli_flag: bool = False,
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Resolve gate: CLI ``True`` **or** env truthy; otherwise default false."""
    env = environ if environ is not None else os.environ
    return bool(cli_flag) or _env_truthy(env.get(ENV_VAR))


def is_attest_rest_for_pregrasp_enabled(
    *,
    cli_flag: bool = False,
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Second gate: explicit attest that Rest draft may arm formal pregrasp."""
    env = environ if environ is not None else os.environ
    return bool(cli_flag) or _env_truthy(env.get(ATTEST_ENV_VAR))


def dual_rest_pregrasp_gates_open(
    *,
    rest_state_capture: bool | None = None,
    attest_rest_for_pregrasp: bool | None = None,
    rest_cli_flag: bool | None = None,
    attest_cli_flag: bool | None = None,
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Both gates must be explicitly open; default path is closed."""
    rest_on = (
        bool(rest_state_capture)
        if rest_state_capture is not None
        else is_rest_state_capture_enabled(cli_flag=bool(rest_cli_flag), environ=environ)
    )
    attest_on = (
        bool(attest_rest_for_pregrasp)
        if attest_rest_for_pregrasp is not None
        else is_attest_rest_for_pregrasp_enabled(
            cli_flag=bool(attest_cli_flag), environ=environ
        )
    )
    return rest_on and attest_on


def rest_state_capture_gate_report(
    *,
    enabled: bool | None = None,
    cli_flag: bool | None = None,
    attest_enabled: bool | None = None,
    attest_cli_flag: bool | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Machine-readable gate status for readiness / evidence."""
    resolved = (
        bool(enabled)
        if enabled is not None
        else is_rest_state_capture_enabled(cli_flag=cli_flag, environ=environ)
    )
    attest_resolved = (
        bool(attest_enabled)
        if attest_enabled is not None
        else is_attest_rest_for_pregrasp_enabled(
            cli_flag=attest_cli_flag, environ=environ
        )
    )
    dual_open = bool(resolved and attest_resolved)
    return {
        "schema_version": "rest-state-capture-gate-0.2",
        "rest_state_capture_available": True,
        "rest_state_capture_enabled": resolved,
        "attest_rest_for_pregrasp_enabled": attest_resolved,
        "dual_gate_open": dual_open,
        "blocked_unless_rest_attested": not dual_open,
        "default_enabled": DEFAULT_ENABLED,
        "default_attest_enabled": DEFAULT_ATTEST_ENABLED,
        "env_var": ENV_VAR,
        "attest_env_var": ATTEST_ENV_VAR,
        "live_arm_via_when_dual_and_valid_draft": (
            LIVE_ARM_VIA_REST_ATTESTED if dual_open else None
        ),
        "ci_never_auto_rest": True,
        "sends_rest_or_opens_can": False,
        "loss_of_hold_not_large_trajectory": True,
        "forbids_enable_motion_trajectory": True,
        "raises_formal_grasp_entry_allowed": dual_open,
        "raises_control_ready": False,
        "counts_as_audited_j6j7_readonly": False,
        "notes": [
            "Rest drops wrist hold; not --enable-motion / large trajectory.",
            "Default false; CI and default paths never auto Rest on hardware.",
            "Dual gate: --rest-state-capture + --attest-rest-for-pregrasp "
            "(or matching env). Only then may a structurally live VALID Rest "
            f"draft arm formal ladder via live_arm_via={LIVE_ARM_VIA_REST_ATTESTED}.",
            "Rest attested ≠ audited J6/J7 readonly; never raises control_ready.",
            f"See {GATE_DOC}.",
        ],
        "code_refs": {
            "gate": "src/brick_stacking/arm/rest_state_capture.py",
            "hardware_capture": "tools/c_left_wrist_rest_capture.py",
            "readonly_hard_block": "src/brick_stacking/arm/v2_wrist_readonly.py",
        },
    }


def is_rest_state_capture_draft(arm_state: Mapping[str, Any] | None) -> bool:
    if not isinstance(arm_state, Mapping):
        return False
    meta = arm_state.get("rest_state_capture")
    if isinstance(meta, Mapping) and meta.get("provenance") == PROVENANCE:
        return True
    reason = str(arm_state.get("reason") or "")
    return reason.startswith("rest_state_capture_draft:")


def _finite(value: Any) -> bool:
    try:
        return type(value) in (float, int) and math.isfinite(float(value))
    except (TypeError, OverflowError, ValueError):
        return False


def _u16_to_rad(u16: int, lo: float, hi: float) -> float:
    if not (0 <= int(u16) <= 65535):
        raise ValueError("position_raw_u16 out of range")
    if not (_finite(lo) and _finite(hi)) or float(lo) >= float(hi):
        raise ValueError("finite ordered theta range required")
    return float(lo) + int(u16) / 65535.0 * (float(hi) - float(lo))


def _wrist_q_from_row(row: Mapping[str, Any], profile: Mapping[str, Any]) -> float:
    mid = int(row["motor_id"])
    config = profile.get(str(mid)) or profile.get(mid)
    if not isinstance(config, Mapping):
        raise ValueError(f"range_profile missing {mid}")
    if config.get("verified") is not True or config.get("units") != "rad":
        raise ValueError(f"range_profile[{mid}] must be verified units=rad")
    lo, hi = config.get("theta_min_rad"), config.get("theta_max_rad")
    if "position_raw_u16" in row:
        return _u16_to_rad(int(row["position_raw_u16"]), float(lo), float(hi))
    raw_hex = row.get("raw_hex")
    if not isinstance(raw_hex, str):
        raise ValueError(f"wrist {mid} needs position_raw_u16 or raw_hex")
    data = bytes.fromhex(raw_hex)
    if len(data) != 8:
        raise ValueError(f"wrist {mid} Rest feedback must be 8 bytes")
    u16 = int.from_bytes(data[1:3], "big")
    return _u16_to_rad(u16, float(lo), float(hi))


def _a7_q_from_row(row: Mapping[str, Any]) -> float:
    if _finite(row.get("position_sdk_rad")):
        return float(row["position_sdk_rad"])
    raw_hex = row.get("raw_hex")
    if not isinstance(raw_hex, str):
        raise ValueError("A7 row needs position_sdk_rad or raw_hex")
    data = bytes.fromhex(raw_hex)
    if not 5 <= len(data) <= 8 or data[0] != 6:
        raise ValueError("A7 position read response required")
    (q,) = struct.unpack("<f", data[1:5])
    if not _finite(q):
        raise ValueError("non-finite A7 position")
    return float(q)


def extract_seven_q_rad_from_rest_capture(
    rest_capture: Mapping[str, Any],
    *,
    range_profile: Mapping[str, Any],
    role: str = "left",
) -> tuple[tuple[float, ...], float, str | None]:
    """Decode seven joint angles from a Rest capture dict (no CAN)."""
    if role not in ENDPOINTS:
        raise ValueError("role must be left or right")
    _channel, _usb, ids = ENDPOINTS[role]
    id_to_joint = {motor_id: JOINTS[index] for index, motor_id in enumerate(ids)}
    received = rest_capture.get("received") or rest_capture.get("received_positions")
    if not isinstance(received, list):
        raise ValueError("rest_capture.received (or received_positions) required")

    positions: dict[int, float] = {}
    stamps: list[float] = []
    for row in received:
        if not isinstance(row, Mapping):
            continue
        if "control_mode" in row and "position_sdk_rad" not in row and "position_raw_u16" not in row:
            continue
        mid = row.get("motor_id")
        if mid not in id_to_joint:
            continue
        mid_i = int(mid)
        if mid_i in positions:
            raise ValueError(f"duplicate motor_id {mid_i}")
        if mid_i in ids[5:]:
            q = _wrist_q_from_row(row, range_profile)
        else:
            q = _a7_q_from_row(row)
        stamp = row.get("host_receive_monotonic_s")
        if not _finite(stamp):
            # Allow mock rows without stamps; use 0.0 placeholder per row order.
            stamp = float(len(stamps))
        positions[mid_i] = q
        stamps.append(float(stamp))

    missing = [mid for mid in ids if mid not in positions]
    if missing:
        raise ValueError(f"incomplete Rest capture; missing motor_ids={missing}")

    q_rad = tuple(positions[mid] for mid in ids)
    host_stamp = max(stamps) if stamps else 0.0
    epoch = rest_capture.get("epoch")
    return q_rad, host_stamp, str(epoch) if epoch else None


def build_live_valid_draft_from_rest(
    rest_capture: Mapping[str, Any],
    *,
    rest_state_capture: bool,
    range_profile: Mapping[str, Any],
    role: str = "left",
    device_id: str | None = None,
    authorization_ref: str | None = None,
    attest_rest_for_pregrasp: bool = False,
) -> dict[str, Any]:
    """Build a structurally live VALID ArmState *draft* from Rest results.

    Requires ``rest_state_capture=True``. Never opens CAN / sends Rest.
    With dual gate (``attest_rest_for_pregrasp=True``) a structurally live
    VALID draft may count for formal arm gate via ``live_arm_via=rest_attested``;
    it still does **not** count as audited J6/J7 readonly and never raises
    ``control_ready``.
    """
    if rest_state_capture is not True:
        raise RestStateCaptureDisabled(
            "rest_state_capture gate is closed (default); refuse Rest draft "
            f"(set --rest-state-capture or {ENV_VAR}=1 for research only)"
        )

    q_rad, host_stamp, epoch = extract_seven_q_rad_from_rest_capture(
        rest_capture, range_profile=range_profile, role=role
    )
    channel, _usb, ids = ENDPOINTS[role]
    resolved_id = device_id or f"{channel}:{','.join(map(str, ids))}"
    auth = authorization_ref or rest_capture.get("authorization_ref")
    validity, base_reason = assign_validity_from_joints(
        positions=list(q_rad), failures=[]
    )
    dual_open = bool(attest_rest_for_pregrasp)
    reason = (
        f"rest_state_capture_draft:{PROVENANCE}; "
        f"auth={auth or 'unspecified'}; "
        f"{base_reason or 'seven_finite_from_rest'}"
    )
    joint_names: tuple[JointName, ...] = JOINTS
    arm_state: ArmState = {
        "sample_id": uuid4().hex,
        "source": "real",
        "device_id": resolved_id,
        "frame_id": f"{role}_arm_base",
        "device_stamp": None,
        "host_receive_stamp": float(host_stamp),
        "clock_domain": "host_monotonic",
        "epoch": epoch or f"rest-draft/{role}/{resolved_id}",
        "validity": validity,
        "reason": reason,
        "joint_names": joint_names,
        "joint_bindings": {
            joint: {"sdk_index": index, "device_joint_id": str(motor_id)}
            for index, (joint, motor_id) in enumerate(zip(joint_names, ids, strict=True))
        },
        "q_rad": q_rad,
        "dq_rad_s": None,
        "enabled": False,
        "fault": None,
        # Extension metadata (ignored by TypedDict consumers that strip extras).
        "rest_state_capture": {  # type: ignore[typeddict-unknown-key]
            "schema_version": DRAFT_SCHEMA,
            "provenance": PROVENANCE,
            "gate_enabled": True,
            "attest_rest_for_pregrasp": dual_open,
            "counts_as_formal_live_valid": dual_open,
            "live_arm_via": LIVE_ARM_VIA_REST_ATTESTED if dual_open else None,
            "counts_as_audited_j6j7_readonly": False,
            "authorization_ref": auth,
            "warning": "Rest removes holding; draft only; no auto re-enable",
            "quantization": "explicit_verified_range_profile",
        },
    }

    classified = classify_arm_state(arm_state)
    gate = rest_state_capture_gate_report(
        enabled=True, attest_enabled=dual_open
    )
    notes = [
        "Rest draft built offline from capture JSON; no CAN / no Rest send.",
        "Default rest_state_capture gate is false; CI must not open this path.",
        "attest_rest_for_pregrasp defaults false; dual gate required for "
        f"formal arm via live_arm_via={LIVE_ARM_VIA_REST_ATTESTED}.",
        "Never raises control_ready; never audited J6/J7 readonly.",
    ]
    if dual_open:
        notes.insert(
            1,
            "Dual gate open: structurally counts_as_live_valid may arm formal "
            f"ladder via live_arm_via={LIVE_ARM_VIA_REST_ATTESTED}.",
        )
    else:
        notes.insert(
            1,
            "Structurally counts_as_live_valid may be true; formal_grasp stays "
            "blocked without --attest-rest-for-pregrasp.",
        )
    payload = emit_live_or_recorded_payload(
        mode="rest-state-capture-draft",
        arm_state=arm_state,
        classification=classified,
        can_opened=False,
        fresh_live_read=False,
        extra_notes=notes,
    )
    payload["rest_state_capture"] = gate
    payload["rest_state_capture"]["draft"] = True
    payload["rest_state_capture"]["counts_as_formal_live_valid"] = dual_open
    payload["rest_state_capture"]["live_arm_via"] = (
        LIVE_ARM_VIA_REST_ATTESTED if dual_open else None
    )
    payload["schema_version"] = DRAFT_SCHEMA
    return payload


# MotorV2 factory COM-Theta comment used by ``motor.angle.angle`` after Rest.
# This is *not* an audited device readback of Flash COM Theta MIN/MAX.
SDK_DEFAULT_THETA_MIN_RAD = -12.5
SDK_DEFAULT_THETA_MAX_RAD = 12.5
SDK_REPORT_PROVENANCE = "sdk_default_pm_12_5_dequantize"
SDK_REPORT_SCHEMA = "rest-sdk-report-angles-0.1"


def sdk_default_u16_to_rad(u16: int) -> float:
    """Dequantize U16 with MotorV2 SDK default ±12.5 rad (unaudited)."""
    return _u16_to_rad(int(u16), SDK_DEFAULT_THETA_MIN_RAD, SDK_DEFAULT_THETA_MAX_RAD)


def annotate_sdk_report_wrist_angles(
    rest_capture: Mapping[str, Any],
) -> dict[str, Any]:
    """Record SDK-style J6/J7 rad from Rest U16 without forging verified ranges.

    ``motor.angle.angle`` after ``MotorV2.read_initial_state`` uses the same
    ±12.5 map. Output is diagnostic only: ``audited_range_profile=false`` and
    must never be written into ``left_wrist_theta_ranges.json`` as verified.
    """
    received = rest_capture.get("received") or rest_capture.get("received_positions")
    if not isinstance(received, list):
        raise ValueError("rest_capture.received (or received_positions) required")

    wrists: dict[str, Any] = {}
    for row in received:
        if not isinstance(row, Mapping):
            continue
        mid = row.get("motor_id")
        if mid not in (66, 67):
            continue
        # Skip Flash mode READ / other non-Rest rows (they also carry raw_hex).
        if "control_mode" in row and "position_raw_u16" not in row:
            continue
        if "position_raw_u16" in row:
            u16 = int(row["position_raw_u16"])
        elif "status" in row and isinstance(row.get("raw_hex"), str):
            data = bytes.fromhex(str(row["raw_hex"]))
            if len(data) != 8:
                raise ValueError(f"wrist {mid} Rest feedback must be 8 bytes")
            u16 = int.from_bytes(data[1:3], "big")
        else:
            continue
        key = str(int(mid))
        if key in wrists:
            raise ValueError(f"duplicate wrist motor_id {key}")
        wrists[key] = {
            "motor_id": int(mid),
            "position_raw_u16": u16,
            "position_sdk_report_rad": sdk_default_u16_to_rad(u16),
            "theta_map_rad": [SDK_DEFAULT_THETA_MIN_RAD, SDK_DEFAULT_THETA_MAX_RAD],
            "provenance": SDK_REPORT_PROVENANCE,
            "audited_range_profile": False,
            "equals_verified_left_wrist_theta_ranges": False,
        }

    missing = [str(m) for m in (66, 67) if str(m) not in wrists]
    if missing:
        raise ValueError(f"incomplete wrist Rest rows; missing motor_ids={missing}")

    return {
        "schema_version": SDK_REPORT_SCHEMA,
        "source": rest_capture.get("source"),
        "capture_id": rest_capture.get("capture_id"),
        "authorization_ref": rest_capture.get("authorization_ref"),
        "wrist": wrists,
        "audited_range_profile": False,
        "may_mark_left_wrist_theta_ranges_verified": False,
        "may_build_rest_draft_as_audited": False,
        "notes": [
            "SDK report rad mirrors MotorV2._dequantize(..., ±12.5, 16) after Rest.",
            "Provenance ≠ audited COM Theta / left_wrist_theta_ranges verified.",
            "Do not set verified=true from this annotation alone.",
        ],
    }


def attempt_rest_draft_or_gap(
    rest_capture: Mapping[str, Any],
    *,
    range_profile: Mapping[str, Any],
    rest_state_capture: bool,
    attest_rest_for_pregrasp: bool = False,
    role: str = "left",
) -> dict[str, Any]:
    """Try dual-gate rest-draft; on unverified ranges return an honest GAP report."""
    sdk_report = annotate_sdk_report_wrist_angles(rest_capture)
    gate = rest_state_capture_gate_report(
        enabled=rest_state_capture, attest_enabled=attest_rest_for_pregrasp
    )
    base: dict[str, Any] = {
        "schema_version": "rest-draft-attempt-0.1",
        "rest_state_capture": gate,
        "sdk_report_angles": sdk_report,
        "control_ready": False,
        "motion_enabled": False,
        "range_profile_verified": {
            "66": bool(
                isinstance(range_profile.get("66"), Mapping)
                and range_profile["66"].get("verified") is True
            ),
            "67": bool(
                isinstance(range_profile.get("67"), Mapping)
                and range_profile["67"].get("verified") is True
            ),
        },
    }
    try:
        draft = build_live_valid_draft_from_rest(
            rest_capture,
            rest_state_capture=rest_state_capture,
            range_profile=range_profile,
            role=role,
            attest_rest_for_pregrasp=attest_rest_for_pregrasp,
        )
    except RestStateCaptureDisabled as exc:
        base.update(
            {
                "verdict": "GATE_CLOSED",
                "pass": False,
                "error": str(exc),
                "draft": None,
            }
        )
        return base
    except ValueError as exc:
        base.update(
            {
                "verdict": "GAP_UNVERIFIED_RANGE_OR_DECODE",
                "pass": False,
                "error": str(exc),
                "draft": None,
                "honest_non_pass": True,
            }
        )
        return base

    draft["control_ready"] = False
    draft["motion_enabled"] = False
    base.update(
        {
            "verdict": "DRAFT_BUILT",
            "pass": True,
            "error": None,
            "draft": draft,
        }
    )
    return base
