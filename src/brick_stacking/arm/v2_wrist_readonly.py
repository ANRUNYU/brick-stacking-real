"""J6/J7 MotorV2 wrist angle — audited read-only path status (hard block).

Audit (2026-11-10 / 2026-11-11, sources: LEFT_STATE_ACQUISITION,
HARDWARE_INTERFACES, c_left_arm_readonly_probe, MotorV2.read_initial_state
review, host SDK ``motor_v2.py`` SHA256
``6f45000ba0f7f049e0a23b7ddceb318154b9672a5181472ea899099ea3127aba``):

* J1–J5: audited A7 ``0x06`` position READ → float32 rad (safe for ArmStateReader).
* J6/J7: audited Flash control-mode READ only (``670b…``) → mode int, **not** angle.
* Angle today requires ``Rest`` (``FF×7+FD`` via ``MotorV2.read_initial_state``) or
  enabled polling feedback whose U16→rad quantization is **not** audited.
* Rest / enable / target / Flash write / large motion are **forbidden** here.
* Exhaustive candidate search found **no** trustworthy position-readonly query
  bytes in-repo or in the pinned host SDK; see ``POSITION_READONLY_CANDIDATES``.

Until an audited read-only position query (exact request bytes + reply layout +
quantization + freshness rules) is recorded, ArmStateReader must leave J6/J7
``q_rad`` as None and ``counts_as_live_valid`` stays false.

This module is a refuse-by-default skeleton. It never opens CAN, never sends
Rest, and never enables motion. Optional live probes must call only paths that
remain in ``AUDITED_SAFE_READS``.

``ENABLE_PENDING_PROTOCOL_AUDIT`` stays **False**: there is no pending query
payload to send. Do not invent Motorevo Flash indices or silent ±12.5 maps.
"""
from __future__ import annotations

from typing import Any

HARD_BLOCK_ID = "j6_j7_no_audited_readonly_position_query"
HARD_BLOCK_DOC = "docs/team/B/J6J7_READONLY_POSITION_HARD_BLOCK_20261110.md"

# Default-closed. Remains False until a vendor-confirmed query lands with
# exact request bytes + reply layout + quantization + freshness rules.
ENABLE_PENDING_PROTOCOL_AUDIT: bool = False

# Set only after a protocol audit lands request/reply bytes + quantization.
# Keeping this None is intentional: callers must not invent a query.
AUDITED_READONLY_POSITION_QUERY_BYTES: bytes | None = None
AUDITED_READONLY_POSITION_REPLY_PREFIX: bytes | None = None
AUDITED_POSITION_QUANTIZATION: dict[str, Any] | None = None

# Pending slot stays empty until Motorevo / scope capture supplies a pure query.
PENDING_PROTOCOL_AUDIT: dict[str, Any] = {
    "enabled_by_default": False,
    "enable_flag": "ENABLE_PENDING_PROTOCOL_AUDIT",
    "position_query_bytes": None,
    "reply_layout": None,
    "quantization": None,
    "counts_as_live_valid_when_enabled": False,
    "reason_empty": (
        "host motor_v2.py + in-repo docs/tools + 2026-11-11 external Web/local "
        "search expose no pure J6/J7 position query; Flash READ index map for "
        "live angle / COM Theta does not exist in SDK or public manuals"
    ),
}

VENDOR_SDK_MOTOR_V2_SHA256 = (
    "6f45000ba0f7f049e0a23b7ddceb318154b9672a5181472ea899099ea3127aba"
)
VENDOR_SDK_MOTOR_V2_PATH = (
    "/home/qwer/linkerbot-p7-unpack/"
    "linkerbot-python-sdk-927290b8e27f9e2df3cc5b0a0776c36e2fb5175e/"
    "src/linkerbot/arm/p7/motor_v2.py"
)

AUDITED_SAFE_READS: tuple[str, ...] = (
    "A7 J1–J5 position READ: CAN id=motor_id, data=0x06 → float32 rad",
    "MotorV2 Flash control-mode READ: id=0x600+motor_id, "
    "data=670b000000000476 → mode int (not angle)",
)

KNOWN_NON_READONLY_OR_UNAUDITED: tuple[str, ...] = (
    "MotorV2.read_initial_state → Rest (FF×7 + FD); changes wrist hold state",
    "tools/host_monitor JointControl._read_angle_locked(J6/J7) → Rest via MotorV2",
    "tools/c_left_wrist_rest_capture.py → explicit Rest (support + auth required)",
    "raw V2 runtime feedback U16 position — quantization / COM Theta not audited",
    "P7 construct / Flash mode write / enable / start_polling / set_angle",
    "MotorV2 state cmds FC (Enter Motor) / FE (Set Zero) — enable or zero side effects",
    "MotorV2 P-T-M control frame — applies PD target; requires Motor state + heartbeat",
)

# Exhaustive in-repo + host-SDK candidate ledger (position angle only).
# "pending_protocol_audit_eligible" means: documented request bytes exist AND
# send path is plausibly side-effect-free. None currently qualify.
POSITION_READONLY_CANDIDATES: tuple[dict[str, Any], ...] = (
    {
        "id": "a7_cmd_0x06_on_v2_ids",
        "sends_motion_rest_or_enable": False,
        "evidence": "weak",
        "verdict": "rejected_no_sdk_path",
        "pending_protocol_audit_eligible": False,
        "notes": (
            "A7 SensorType.POSITION=0x06 is A7Motor-only; MotorV2 has no "
            "_read_register / 0x06 path; readonly probe never sends 0x06 to 66/67"
        ),
    },
    {
        "id": "flash_control_mode_0x0b",
        "sends_motion_rest_or_enable": False,
        "evidence": "strong_audited",
        "verdict": "rejected_not_angle",
        "pending_protocol_audit_eligible": False,
        "request_bytes_hex": "670b000000000476",
        "notes": "Audited Flash READ returns mode int; not encoder angle",
    },
    {
        "id": "flash_generic_read_unknown_theta_indices",
        "sends_motion_rest_or_enable": False,
        "evidence": "protocol_shape_only",
        "verdict": "rejected_index_map_missing",
        "pending_protocol_audit_eligible": False,
        "notes": (
            "motor_v2._read_flash_param(index) is a generic READ (cmd 0x04) but "
            "SDK only defines indices 0x00=SAVE and 0x0B=CONTROL_MODE; COM Theta "
            "MIN/MAX indices are named in comments without numbers — guessing "
            "forbidden; even correct indices yield range params, not live q_rad"
        ),
    },
    {
        "id": "rest_ff7_fd_read_initial_state",
        "sends_motion_rest_or_enable": True,
        "evidence": "strong_sdk_and_field",
        "verdict": "rejected_side_effect",
        "pending_protocol_audit_eligible": False,
        "request_bytes_hex": "fffffffffffffffd",
        "notes": "Only SDK path that solicits angle without enable; loses hold",
    },
    {
        "id": "enter_motor_fc_or_ptm_stream",
        "sends_motion_rest_or_enable": True,
        "evidence": "strong_sdk",
        "verdict": "rejected_side_effect",
        "pending_protocol_audit_eligible": False,
        "notes": "FC enters Motor; P-T-M frames apply targets + need heartbeat",
    },
    {
        "id": "passive_can_listen",
        "sends_motion_rest_or_enable": False,
        "evidence": "field_C21",
        "verdict": "rejected_no_frames",
        "pending_protocol_audit_eligible": False,
        "notes": "3s passive window on 61–67 observed 0 frames when idle",
    },
    {
        "id": "host_monitor_j6j7_read_angle",
        "sends_motion_rest_or_enable": True,
        "evidence": "strong_code",
        "verdict": "rejected_side_effect",
        "pending_protocol_audit_eligible": False,
        "notes": "JointControl._read_angle_locked → MotorV2.read_initial_state Rest",
    },
    {
        "id": "sdk_default_pm_12_5_u16_map",
        "sends_motion_rest_or_enable": "depends_on_feed",
        "evidence": "sdk_default_unverified",
        "verdict": "rejected_quantization_unaudited",
        "pending_protocol_audit_eligible": False,
        "notes": (
            "±12.5 rad factory comment is not device readback; left_wrist_theta_"
            "ranges.json remains null/verified=false"
        ),
    },
)

EXTERNAL_NEXT_STEPS: tuple[str, ...] = (
    "Obtain Motorevo CAN protocol manual (SDK cites §6.3.2 for P-T-M packing) "
    "with: (a) any pure status/position query command that is not Rest/FC/FE/"
    "P-T-M target, exact 8-byte request + reply layout; OR written confirmation "
    "that no such query exists.",
    "If Flash holds live/comm parameters: vendor Flash index map for CAN COM "
    "Theta MIN/MAX (and any live-position index if one exists) — do not brute-"
    "force indices on the arm.",
    "Optional authorized scope/candump of one braced Rest vs one P-T-M heartbeat "
    "on a supported wrist to cross-check feedback layout only — still not a "
    "formal readonly API unless the manual names a side-effect-free query.",
    "Public Motorevo product pages do not publish the protocol PDF; contact "
    "vendor (e.g. sales@mail.motorevo.cn) or LinkerBot for the drive manual "
    "matching this Flash/P-T-M stack.",
)

# 2026-11-11 out-of-repo search (Web + local readonly). Negative: no payload.
EXTERNAL_PROTOCOL_SEARCH: dict[str, Any] = {
    "schema_version": "j6j7-external-protocol-search-0.1",
    "searched_at_local": "2026-11-11T00:23:00+08:00",
    "evidence_json": (
        "docs/team/B/evidence/field_20261110/"
        "j6j7_external_protocol_search_20261111.json"
    ),
    "motorevo_protocol_manual_found": False,
    "flash_theta_index_map_found": False,
    "pure_position_query_bytes_found": False,
    "pending_protocol_audit_payload_landed": False,
    "goal_complete": False,
    "public_motor_v2_main_sha256": (
        "6f45000ba0f7f049e0a23b7ddceb318154b9672a5181472ea899099ea3127aba"
    ),
    "negative_conclusion": (
        "Round 00:23: Motorevo-Studio EXE-only; public motor_v2 SHA now matches "
        "host pin but Flash still SAVE/CONTROL_MODE only — no pure query / Theta "
        "index; pending_protocol_audit stays empty/default-off."
    ),
}

FAILURE_REASON = "J6/J7: no audited read-only position query"
ARM_STATE_READER_LIVE_HOLD: tuple[str, ...] = (
    "J6/J7: no audited read-only position query (ArmStateReader leaves q_rad None)",
    "validity remains INVALID until seven finite joint angles are available",
    "Rest/raw V2 capture is not an audited read-only path and is not used here",
    "candidate search 2026-11-11: no pending_protocol_audit position payload",
    "external protocol search 2026-11-11: no Motorevo manual / Theta index",
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


def candidate_search_report() -> dict[str, Any]:
    """Machine-readable outcome of the position-readonly candidate sweep."""
    eligible = [
        c["id"]
        for c in POSITION_READONLY_CANDIDATES
        if c.get("pending_protocol_audit_eligible")
    ]
    return {
        "schema_version": "j6j7-position-readonly-candidate-search-0.1",
        "searched_at_utc": "2026-11-10T16:00:00Z",
        "vendor_sdk_motor_v2_sha256": VENDOR_SDK_MOTOR_V2_SHA256,
        "vendor_sdk_motor_v2_path": VENDOR_SDK_MOTOR_V2_PATH,
        "position_readonly_candidate_found": False,
        "pending_protocol_audit_eligible_ids": eligible,
        "enable_pending_protocol_audit": ENABLE_PENDING_PROTOCOL_AUDIT,
        "pending_protocol_audit": dict(PENDING_PROTOCOL_AUDIT),
        "candidates": [dict(c) for c in POSITION_READONLY_CANDIDATES],
        "external_next_steps": list(EXTERNAL_NEXT_STEPS),
        "external_protocol_search": dict(EXTERNAL_PROTOCOL_SEARCH),
        "goal_software_only_completable": False,
        "counts_as_live_valid_reachable_via_readonly": False,
        "notes": [
            "No in-repo / host-SDK / external-search pure J6/J7 position query; "
            "formal grasp remains blocked on j6_j7_readonly until vendor "
            "protocol lands.",
            "Do not raise control_ready / forge live VALID / enable-motion.",
            "Do not re-spin the same eight in-repo candidates; need vendor input.",
        ],
    }


def hard_block_report() -> dict[str, Any]:
    """Machine-readable hard-block status for readiness / evidence."""
    search = candidate_search_report()
    return {
        "schema_version": "j6j7-readonly-position-hard-block-0.2",
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
        "enable_pending_protocol_audit": ENABLE_PENDING_PROTOCOL_AUDIT,
        "pending_protocol_audit": dict(PENDING_PROTOCOL_AUDIT),
        "position_readonly_candidate_found": False,
        "candidate_search": search,
        "external_protocol_search": dict(EXTERNAL_PROTOCOL_SEARCH),
        "goal_complete": False,
        "doc": HARD_BLOCK_DOC,
        "notes": [
            "Do not call MotorV2.read_initial_state from ArmStateReader.",
            "Flash mode READ remains allowed for binding identity only.",
            "Live VALID requires a future audited query; until then formal grasp stays blocked.",
            "2026-11-11 candidate sweep + external Web/local search: zero pending "
            "position payloads; need Motorevo manual / Flash Theta index / capture auth.",
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
    Never activates under ``ENABLE_PENDING_PROTOCOL_AUDIT`` alone while pending
    payload is empty.
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
    enable_pending_protocol_audit: bool | None = None,
) -> dict[str, Any]:
    """Best-effort entry for a future audited / pending-audit readonly path.

    Always soft-fails today: returns a hard-block report without touching the
    bus. Callers must not fall back to Rest. Pending switch defaults False and
    has no payload — enabling it still refuses bus I/O.
    """
    del motor_ids  # reserved for a future audited query loop
    pending_on = (
        ENABLE_PENDING_PROTOCOL_AUDIT
        if enable_pending_protocol_audit is None
        else bool(enable_pending_protocol_audit)
    )
    pending_bytes = PENDING_PROTOCOL_AUDIT.get("position_query_bytes")
    report = hard_block_report()
    report["enable_pending_protocol_audit_effective"] = pending_on

    if pending_on and pending_bytes is None:
        return {
            **report,
            "attempted": False,
            "bus_touched": False,
            "q_rad": (None, None),
            "live_draft": None,
            "counts_as_live_valid": False,
            "error": (
                f"{HARD_BLOCK_ID}: pending_protocol_audit enabled but "
                "position_query_bytes is empty; refuse bus (need Motorevo manual)"
            ),
        }

    if bus is not None and AUDITED_READONLY_POSITION_QUERY_BYTES is None:
        # Explicit refuse even if a bus handle was passed — never send Rest.
        return {
            **report,
            "attempted": False,
            "bus_touched": False,
            "q_rad": (None, None),
            "live_draft": None,
            "counts_as_live_valid": False,
            "error": f"{HARD_BLOCK_ID}: refuse bus use until audited query bytes exist",
        }
    return {
        **report,
        "attempted": False,
        "bus_touched": False,
        "q_rad": (None, None),
        "live_draft": None,
        "counts_as_live_valid": False,
        "error": None,
    }
