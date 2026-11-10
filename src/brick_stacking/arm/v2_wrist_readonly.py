"""J6/J7 MotorV2 wrist angle — audited read-only path status (hard block).

Audit (2026-11-10, sources: LEFT_STATE_ACQUISITION, HARDWARE_INTERFACES,
c_left_arm_readonly_probe, MotorV2.read_initial_state review):

* J1–J5: audited A7 ``0x06`` position READ → float32 rad (safe for ArmStateReader).
* J6/J7: audited Flash control-mode READ only (``670b…``) → mode int, **not** angle.
* Angle today requires ``Rest`` (``FF×7+FD`` via ``MotorV2.read_initial_state``) or
  enabled polling feedback whose U16→rad quantization is **not** audited.
* Rest / enable / target / Flash write / large motion are **forbidden** here.

Until an audited read-only position query (exact request bytes + reply layout +
quantization + freshness rules) is recorded, ArmStateReader must leave J6/J7
``q_rad`` as None and ``counts_as_live_valid`` stays false.

This module is a refuse-by-default skeleton. It never opens CAN, never sends
Rest, and never enables motion. Optional live probes must call only paths that
remain in ``AUDITED_SAFE_READS``.
"""
from __future__ import annotations

from typing import Any

HARD_BLOCK_ID = "j6_j7_no_audited_readonly_position_query"
HARD_BLOCK_DOC = "docs/team/B/J6J7_READONLY_POSITION_HARD_BLOCK_20261110.md"

# Set only after a protocol audit lands request/reply bytes + quantization.
# Keeping this None is intentional: callers must not invent a query.
AUDITED_READONLY_POSITION_QUERY_BYTES: bytes | None = None
AUDITED_READONLY_POSITION_REPLY_PREFIX: bytes | None = None
AUDITED_POSITION_QUANTIZATION: dict[str, Any] | None = None

AUDITED_SAFE_READS: tuple[str, ...] = (
    "A7 J1–J5 position READ: CAN id=motor_id, data=0x06 → float32 LE rad",
    "MotorV2 Flash control-mode READ: id=0x600+motor_id, "
    "data=670b000000000476 → mode int (not angle)",
)

KNOWN_NON_READONLY_OR_UNAUDITED: tuple[str, ...] = (
    "MotorV2.read_initial_state → Rest (FF×7 + FD); changes wrist hold state",
    "tools/host_monitor JointControl._read_angle_locked(J6/J7) → Rest via MotorV2",
    "tools/c_left_wrist_rest_capture.py → explicit Rest (support + auth required)",
    "raw V2 runtime feedback U16 position — quantization / COM Theta not audited",
    "P7 construct / Flash mode write / enable / start_polling / set_angle",
)

FAILURE_REASON = "J6/J7: no audited read-only position query"
ARM_STATE_READER_LIVE_HOLD: tuple[str, ...] = (
    "J6/J7: no audited read-only position query (ArmStateReader leaves q_rad None)",
    "validity remains INVALID until seven finite joint angles are available",
    "Rest/raw V2 capture is not an audited read-only path and is not used here",
)


class J6J7ReadonlyPositionHardBlock(RuntimeError):
    """Raised when a caller asks for J6/J7 rad without an audited readonly query."""

    def __init__(self, detail: str | None = None) -> None:
        message = detail or (
            f"{HARD_BLOCK_ID}: no audited MotorV2 read-only position query; "
            f"see {HARD_BLOCK_DOC}. Refuse Rest/enable/motion."
        )
        super().__init__(message)
        self.hard_block_id = HARD_BLOCK_ID


def hard_block_report() -> dict[str, Any]:
    """Machine-readable hard-block status for readiness / evidence."""
    return {
        "schema_version": "j6j7-readonly-position-hard-block-0.1",
        "id": HARD_BLOCK_ID,
        "status": "HARD_BLOCK",
        "audited_readonly_position_query_available": False,
        "audited_readonly_position_query_bytes": None,
        "audited_position_quantization": None,
        "audited_safe_reads": list(AUDITED_SAFE_READS),
        "known_non_readonly_or_unaudited": list(KNOWN_NON_READONLY_OR_UNAUDITED),
        "failure_reason": FAILURE_REASON,
        "arm_state_reader_live_hold": list(ARM_STATE_READER_LIVE_HOLD),
        "counts_as_live_valid_reachable_via_readonly": False,
        "allows_rest": False,
        "allows_enable_motion": False,
        "allows_large_joint_motion": False,
        "doc": HARD_BLOCK_DOC,
        "notes": [
            "Do not call MotorV2.read_initial_state from ArmStateReader.",
            "Flash mode READ remains allowed for binding identity only.",
            "Live VALID requires a future audited query; until then formal grasp stays blocked.",
        ],
    }


def decode_audited_wrist_position_reply(
    *,
    motor_id: int,
    reply: bytes,
) -> float:
    """Skeleton decoder for a future audited J6/J7 position reply.

    Refuses until ``AUDITED_READONLY_POSITION_QUERY_BYTES`` and quantization
    are filled from a protocol audit. Never treats Rest/raw feedback as audited.
    """
    if motor_id not in {56, 57, 66, 67}:
        raise ValueError(f"motor_id {motor_id} is not a V2 wrist id")
    if AUDITED_READONLY_POSITION_QUERY_BYTES is None:
        raise J6J7ReadonlyPositionHardBlock(
            "decode refused: AUDITED_READONLY_POSITION_QUERY_BYTES is unset"
        )
    if AUDITED_POSITION_QUANTIZATION is None:
        raise J6J7ReadonlyPositionHardBlock(
            "decode refused: AUDITED_POSITION_QUANTIZATION is unset"
        )
    prefix = AUDITED_READONLY_POSITION_REPLY_PREFIX
    if prefix is not None and not reply.startswith(prefix):
        raise ValueError("reply prefix mismatch for audited V2 position query")
    # Intentional: no silent default ±12.5 rad map.
    raise J6J7ReadonlyPositionHardBlock(
        "decode skeleton has no audited quantization implementation yet"
    )


def try_read_wrist_positions_readonly(
    *,
    motor_ids: tuple[int, int] = (66, 67),
    bus: Any = None,
) -> dict[str, Any]:
    """Best-effort entry for a future audited readonly path.

    Always soft-fails today: returns a hard-block report without touching the
    bus. Callers must not fall back to Rest.
    """
    del motor_ids  # reserved for a future audited query loop
    if bus is not None and AUDITED_READONLY_POSITION_QUERY_BYTES is None:
        # Explicit refuse even if a bus handle was passed — never send Rest.
        return {
            **hard_block_report(),
            "attempted": False,
            "bus_touched": False,
            "q_rad": (None, None),
            "error": f"{HARD_BLOCK_ID}: refuse bus use until audited query bytes exist",
        }
    return {
        **hard_block_report(),
        "attempted": False,
        "bus_touched": False,
        "q_rad": (None, None),
        "error": None,
    }
