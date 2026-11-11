"""T1 bounded live runner skeleton (default motion OFF).

T1 subset preferred for first hardware contact:
  Rest seven-axis capture → optional low-speed single-joint / short empty run.

This module never opens CAN, never sends Rest, never enables motion, and never
raises ``control_ready``. It only validates prerequisites and emits a dry-run
plan / refuse report. Full PlanBundle live execution is intentionally absent.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

SCHEMA = "t1-bounded-live-runner-0.1"
SHORT_COMBO_SCHEMA = "t1-bounded-short-combo-0.1"
DEFAULT_MOTION_ENABLED = False
DEFAULT_CONTROL_READY = False
MAX_SINGLE_JOINT_STEP_RAD = 0.05  # hard cap for any future enable path
MAX_SHORT_COMBO_STEPS = 8
MAX_SHORT_COMBO_STEP_DEG = 1.0  # live/host_monitor soft cap for short combo
ALLOWED_JOINTS_FIRST_PASS = ("J1", "J2", "J3", "J4", "J5")  # wrist later
ALLOWED_SHORT_COMBO_JOINTS = (1, 2, 3, 4, 5)  # wrist MOVE still forbidden here


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def evaluate_t1_prerequisites(
    *,
    rest_capture: Mapping[str, Any] | None = None,
    rest_draft_attempt: Mapping[str, Any] | None = None,
    range_profile: Mapping[str, Any] | None = None,
    urdf_available: bool = False,
    motion_enabled: bool = False,
    control_ready: bool = False,
    block_present: bool = False,
) -> dict[str, Any]:
    """Gate checklist for T1 empty run. Defaults refuse motion."""
    capture = _mapping(rest_capture)
    draft = _mapping(rest_draft_attempt)
    profile = _mapping(range_profile)

    rest_ok = capture.get("status") == "RAW_SEVEN_AXIS_CAPTURED"
    j1_j5_ok = False
    if rest_ok:
        received = capture.get("received") or capture.get("received_positions") or []
        a7 = [
            r
            for r in received
            if isinstance(r, Mapping)
            and r.get("motor_id") in range(61, 66)
            and r.get("position_sdk_rad") is not None
        ]
        j1_j5_ok = len(a7) >= 5

    verified_66 = bool(
        isinstance(profile.get("66"), Mapping) and profile["66"].get("verified") is True
    )
    verified_67 = bool(
        isinstance(profile.get("67"), Mapping) and profile["67"].get("verified") is True
    )
    wrist_audited = verified_66 and verified_67
    draft_pass = draft.get("pass") is True and draft.get("verdict") == "DRAFT_BUILT"

    blocked_by: list[str] = []
    if not rest_ok:
        blocked_by.append("missing_raw_seven_axis_rest_capture")
    if not j1_j5_ok:
        blocked_by.append("j1_j5_sdk_angles_incomplete")
    if not wrist_audited:
        blocked_by.append("j6_j7_range_profile_unverified")
    if not draft_pass:
        blocked_by.append("rest_draft_not_pass")
    if not urdf_available:
        blocked_by.append("p7_urdf_not_wired_into_runner")
    if block_present:
        blocked_by.append("block_present_t1_requires_empty")
    if motion_enabled:
        blocked_by.append("motion_enabled_refused_by_default_skeleton")
    if control_ready:
        blocked_by.append("control_ready_must_stay_false_here")

    # First-pass T1 subset may proceed to *planning only* with J1–J5 + Rest raw,
    # still without motion, if Rest captured and no block.
    subset_plan_allowed = bool(rest_ok and j1_j5_ok and not block_present)
    live_motion_allowed = False  # skeleton never opens motion

    return {
        "schema_version": SCHEMA,
        "t1_level": "empty_run_no_block",
        "subset": "rest_then_optional_single_joint_or_short_traj",
        "rest_capture_ok": rest_ok,
        "j1_j5_sdk_ok": j1_j5_ok,
        "wrist_range_audited": wrist_audited,
        "rest_draft_pass": draft_pass,
        "urdf_available": bool(urdf_available),
        "block_present": bool(block_present),
        "motion_enabled": False,
        "control_ready": False,
        "default_motion_enabled": DEFAULT_MOTION_ENABLED,
        "default_control_ready": DEFAULT_CONTROL_READY,
        "subset_dry_plan_allowed": subset_plan_allowed,
        "live_motion_allowed": live_motion_allowed,
        "full_plan_bundle_live_executor": False,
        "blocked_by": blocked_by,
        "notes": [
            "Prefer Rest→low-speed single-joint/short empty path over synthetic PlanBundle.",
            "Skeleton refuses --enable-motion / control_ready elevation.",
            "J6/J7 audited range still required before wrist motion or audited rest-draft PASS.",
            "host_monitor single-joint --enable-motion remains a separate, explicit path.",
        ],
    }


def build_t1_bounded_dry_plan(
    *,
    rest_capture: Mapping[str, Any],
    joint: str = "J1",
    step_rad: float = 0.02,
    prerequisites: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Emit a non-executable single-joint empty-run plan from Rest J1–J5 seeds."""
    prereq = (
        dict(prerequisites)
        if prerequisites is not None
        else evaluate_t1_prerequisites(rest_capture=rest_capture)
    )
    if joint not in ALLOWED_JOINTS_FIRST_PASS:
        raise ValueError(f"first-pass T1 joint must be one of {ALLOWED_JOINTS_FIRST_PASS}")
    step = float(step_rad)
    if not (0.0 < abs(step) <= MAX_SINGLE_JOINT_STEP_RAD):
        raise ValueError(f"step_rad must be in (0, {MAX_SINGLE_JOINT_STEP_RAD}]")

    received = rest_capture.get("received") or rest_capture.get("received_positions") or []
    seeds: dict[str, float] = {}
    name_by_id = {61: "J1", 62: "J2", 63: "J3", 64: "J4", 65: "J5"}
    for row in received:
        if not isinstance(row, Mapping):
            continue
        mid = row.get("motor_id")
        if mid in name_by_id and row.get("position_sdk_rad") is not None:
            seeds[name_by_id[int(mid)]] = float(row["position_sdk_rad"])

    if joint not in seeds:
        raise ValueError(f"Rest capture missing SDK angle for {joint}")

    start = seeds[joint]
    target = start + step
    executable = False
    refuse_reason = None
    if not prereq.get("subset_dry_plan_allowed"):
        refuse_reason = "prerequisites_blocked:" + ",".join(prereq.get("blocked_by") or [])
    if prereq.get("live_motion_allowed") is not True:
        # Always true for this skeleton — keep explicit.
        refuse_reason = refuse_reason or "live_motion_disabled_by_skeleton"

    return {
        "schema_version": SCHEMA,
        "kind": "t1_single_joint_empty_dry_plan",
        "executable": executable,
        "motion_enabled": False,
        "control_ready": False,
        "joint": joint,
        "start_rad": start,
        "target_rad": target,
        "step_rad": step,
        "max_step_rad": MAX_SINGLE_JOINT_STEP_RAD,
        "seed_source": "rest_capture_j1_j5_position_sdk_rad",
        "wrist_j6_j7_commanded": False,
        "block_present": False,
        "refuse_reason": refuse_reason,
        "prerequisites": prereq,
        "next_hardware_step": (
            "operator-reviewed host_monitor single-joint OR future enable-gated "
            "runner; still T1 empty, no block"
        ),
    }


def default_short_combo_waypoints(
    *,
    joints: Sequence[int] = (1, 2, 3),
    step_deg: float = 1.0,
) -> list[dict[str, Any]]:
    """Build outbound then return waypoints (one joint at a time).

    Example with joints=(1,2,3): J1+ → J2+ → J3+ → J3− → J2− → J1−.
    """
    step = float(step_deg)
    if not (0.0 < step <= MAX_SHORT_COMBO_STEP_DEG):
        raise ValueError(f"step_deg must be in (0, {MAX_SHORT_COMBO_STEP_DEG}]")
    ordered = [int(j) for j in joints]
    if not ordered:
        raise ValueError("joints must be non-empty")
    if len(ordered) > MAX_SHORT_COMBO_STEPS // 2:
        raise ValueError(
            f"at most {MAX_SHORT_COMBO_STEPS // 2} joints for out-and-back "
            f"(hard cap {MAX_SHORT_COMBO_STEPS} steps)"
        )
    for joint in ordered:
        if joint not in ALLOWED_SHORT_COMBO_JOINTS:
            raise ValueError(
                f"short-combo joint must be one of {ALLOWED_SHORT_COMBO_JOINTS}"
            )
    waypoints: list[dict[str, Any]] = []
    for joint in ordered:
        waypoints.append(
            {
                "joint": joint,
                "step_deg": step,
                "direction": 1,
                "phase": "outbound",
            }
        )
    for joint in reversed(ordered):
        waypoints.append(
            {
                "joint": joint,
                "step_deg": step,
                "direction": -1,
                "phase": "return",
            }
        )
    return waypoints


def build_t1_short_combo_dry_plan(
    *,
    waypoints: Sequence[Mapping[str, Any]] | None = None,
    joints: Sequence[int] = (1, 2, 3),
    step_deg: float = 1.0,
    rest_capture: Mapping[str, Any] | None = None,
    prerequisites: Mapping[str, Any] | None = None,
    motion_enabled: bool = False,
    authorization_ref: str | None = None,
) -> dict[str, Any]:
    """Emit a non-executable short combo empty-run plan (default motion OFF).

    This is intentionally *not* a synthetic H3 / PlanBundle trajectory. Live
    motion requires a separate explicit enable path (host_monitor runner).
    """
    prereq = (
        dict(prerequisites)
        if prerequisites is not None
        else evaluate_t1_prerequisites(rest_capture=rest_capture)
    )
    pts = (
        [dict(p) for p in waypoints]
        if waypoints is not None
        else default_short_combo_waypoints(joints=joints, step_deg=step_deg)
    )
    if not pts:
        raise ValueError("waypoints must be non-empty")
    if len(pts) > MAX_SHORT_COMBO_STEPS:
        raise ValueError(f"at most {MAX_SHORT_COMBO_STEPS} waypoints")

    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(pts):
        joint = int(raw["joint"])
        if joint not in ALLOWED_SHORT_COMBO_JOINTS:
            raise ValueError(
                f"waypoint[{index}] joint must be one of {ALLOWED_SHORT_COMBO_JOINTS}"
            )
        step = float(raw.get("step_deg", step_deg))
        if not (0.0 < step <= MAX_SHORT_COMBO_STEP_DEG):
            raise ValueError(
                f"waypoint[{index}] step_deg must be in (0, {MAX_SHORT_COMBO_STEP_DEG}]"
            )
        direction = int(raw.get("direction", 1))
        if direction not in (-1, 0, 1):
            raise ValueError(f"waypoint[{index}] direction must be -1, 0, or 1")
        normalized.append(
            {
                "index": index,
                "joint": joint,
                "step_deg": step,
                "direction": direction,
                "phase": str(raw.get("phase") or "unspecified"),
            }
        )

    refuse_reason = None
    if motion_enabled:
        refuse_reason = "motion_enabled_refused_by_default_skeleton"
    if prereq.get("live_motion_allowed") is not True:
        refuse_reason = refuse_reason or "live_motion_disabled_by_skeleton"

    return {
        "schema_version": SHORT_COMBO_SCHEMA,
        "kind": "t1_short_combo_empty_dry_plan",
        "executable": False,
        "motion_enabled": False,
        "control_ready": False,
        "authorization_ref": authorization_ref,
        "waypoints": normalized,
        "waypoint_count": len(normalized),
        "max_waypoints": MAX_SHORT_COMBO_STEPS,
        "max_step_deg": MAX_SHORT_COMBO_STEP_DEG,
        "wrist_j6_j7_commanded_move": False,
        "block_present": False,
        "fail_stop": True,
        "provenance": {
            "trajectory_kind": "joint_space_host_monitor_sequence",
            "not_h3_plan_bundle": True,
            "not_synthetic_fk_ik_bundle": True,
            "urdf_role": "soft_limits_inside_host_monitor_joint_control_only",
            "fk_ik_live_wiring": "not_claimed",
        },
        "refuse_reason": refuse_reason,
        "prerequisites": prereq,
        "next_hardware_step": (
            "tools/t1_bounded_short_combo_runner.py with explicit "
            "--enable-live-motion on host_monitor; still T1 empty, no block"
        ),
    }


def summarize_t1_status(
    *,
    rest_capture: Mapping[str, Any] | None = None,
    rest_draft_attempt: Mapping[str, Any] | None = None,
    range_profile: Mapping[str, Any] | None = None,
    urdf_available: bool = False,
) -> dict[str, Any]:
    """Compact status blob for LIVE_GATE / evidence."""
    prereq = evaluate_t1_prerequisites(
        rest_capture=rest_capture,
        rest_draft_attempt=rest_draft_attempt,
        range_profile=range_profile,
        urdf_available=urdf_available,
    )
    dry = None
    short_combo = None
    if rest_capture and prereq.get("subset_dry_plan_allowed"):
        dry = build_t1_bounded_dry_plan(rest_capture=rest_capture, prerequisites=prereq)
        short_combo = build_t1_short_combo_dry_plan(
            rest_capture=rest_capture, prerequisites=prereq
        )
    return {
        "schema_version": SCHEMA,
        "prerequisites": prereq,
        "dry_plan": dry,
        "short_combo_dry_plan": short_combo,
        "live_executor_present": False,
        "software_plan_bundle_not_live_trajectory": True,
    }
