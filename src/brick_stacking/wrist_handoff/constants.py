"""Frozen Line H constants from TWO_LINE_WRIST_PLAN_20261111."""

from __future__ import annotations

JOINT_NAMES = ("J1", "J2", "J3", "J4", "J5", "J6", "J7")
SDK_MOTOR_IDS = (61, 62, 63, 64, 65, 66, 67)
HAND_CHANNEL_NAMES = (
    "thumb_flex",
    "thumb_abd",
    "index",
    "middle",
    "ring",
    "pinky",
)
PARENT_FRAME = "L_arm_root"
CHILD_FRAME = "L8_Link"
LOCKED_URDF_SHA256 = "233a0fd9e6ce53a5aca9001b77714598ae5d9d996b084546f5efc55230f7edce"
BOARD_SQUARE_SIZE_M = 0.01938
BOARD_INNER_CORNERS = (9, 6)

DEFAULT_LIMITS = {
    "cartesian_arrival_max_m": 0.01,
    "level_travel_clearance_m": 0.08,
    "lift_before_travel_m": 0.03,
    "max_tcp_speed_m_s": 0.02,
    "table_height_check_max_m": 0.008,
}

SEED_PROVENANCE_DEFAULT = (
    "sdk_audited",
    "sdk_audited",
    "sdk_audited",
    "sdk_audited",
    "sdk_audited",
    "sdk_report_not_audited",
    "sdk_report_not_audited",
)
