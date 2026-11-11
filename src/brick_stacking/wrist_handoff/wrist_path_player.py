"""Left-arm wrist-path-0.1 player (default dry-run; no finger commands).

Live dispatch (when separately authorized) uses coordinated seven-axis
``linkerbot.P7.move_j([J1..J7])`` — never host_monitor single-joint MOVE, never
O6/hand, never right arm, never Rest.

J6/J7 remain ``sdk_report_not_audited``. Readonly host_monitor snapshots may
carry null wrist angles; this module refuses rather than inventing them.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from brick_stacking.localization.urdf_chain import urdf_forward_kinematics
from brick_stacking.wrist_handoff.constants import (
    CHILD_FRAME,
    DEFAULT_LIMITS,
    JOINT_NAMES,
    LOCKED_URDF_SHA256,
    PARENT_FRAME,
    SEED_PROVENANCE_DEFAULT,
)

SCHEMA = "wrist-path-left-player-0.1"
LOCKED_URDF_REL = Path("config/models/p7_left/p7__left.urdf")
URDF_JOINTS = tuple(f"L{i}_Joint" for i in range(1, 8))
J2_MIN_RAD = -0.07
ARRIVAL_MAX_M = float(DEFAULT_LIMITS["cartesian_arrival_max_m"])
MAX_TCP_SPEED_M_S = float(DEFAULT_LIMITS["max_tcp_speed_m_s"])
MOTION_BACKEND_KIND = "linkerbot_P7_move_j_seven_axis_coordinated"
FORBIDDEN_BACKENDS = (
    "host_monitor_single_joint",
    "t1_bounded_short_combo",
    "mock_arm_replay_single_block",
)


class CoordinatedSevenAxisArm(Protocol):
    """Seven joints move together; no hand / Rest / right-arm surface."""

    backend_kind: str

    def read_q_rad(self) -> tuple[float, float, float, float, float, float, float]: ...

    def move_j_seven(
        self,
        q_rad: Sequence[float],
        *,
        duration_s: float | None = None,
    ) -> None: ...

    def close(self) -> None: ...


@dataclass
class RecordingSevenAxisArm:
    """Test double: records coordinated 7-vectors; never touches a hand API."""

    initial_q_rad: Sequence[float]
    backend_kind: str = "recording_seven_axis_mock"
    moves: list[dict[str, Any]] = field(default_factory=list)
    hand_commands: list[Any] = field(default_factory=list)
    rest_commands: list[Any] = field(default_factory=list)
    right_arm_commands: list[Any] = field(default_factory=list)
    _q: list[float] = field(init=False)

    def __post_init__(self) -> None:
        q = _require_finite_seven(self.initial_q_rad, "initial_q_rad")
        self._q = list(q)

    def read_q_rad(self) -> tuple[float, float, float, float, float, float, float]:
        return tuple(self._q)  # type: ignore[return-value]

    def move_j_seven(
        self,
        q_rad: Sequence[float],
        *,
        duration_s: float | None = None,
    ) -> None:
        q = _require_finite_seven(q_rad, "move_j_seven q_rad")
        if len(q) != 7:
            raise ValueError("coordinated move requires exactly seven joints")
        self.moves.append(
            {
                "q_rad": list(q),
                "duration_s": None if duration_s is None else float(duration_s),
                "joint_count": 7,
                "single_joint": False,
            }
        )
        self._q = list(q)

    def close(self) -> None:
        return None


def file_sha256_lf(path: Path | str) -> str:
    """SHA-256 of LF-normalized bytes (Windows CRLF checkouts stay comparable)."""
    raw = Path(path).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(raw).hexdigest()


def _require_finite_seven(
    values: Sequence[Any], field_name: str
) -> tuple[float, float, float, float, float, float, float]:
    if values is None or len(values) != 7:
        raise ValueError(f"{field_name} requires seven values")
    out: list[float] = []
    for i, v in enumerate(values):
        if v is None:
            raise ValueError(
                f"{field_name}[{i}] is null; refuse inventing J6/J7 or any missing angle"
            )
        try:
            f = float(v)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name}[{i}] is not a finite float") from exc
        if not math.isfinite(f):
            raise ValueError(f"{field_name}[{i}] is not a finite float")
        out.append(f)
    return (out[0], out[1], out[2], out[3], out[4], out[5], out[6])


def parse_q_rad_from_state(state: Mapping[str, Any] | Sequence[Any]) -> tuple[float, ...]:
    """Accept a bare 7-list or host_monitor-like arm snapshot.

    Explicitly refuses null J6/J7 (common on readonly host_monitor).
    """
    if isinstance(state, Mapping):
        if "q_rad" in state:
            return _require_finite_seven(state["q_rad"], "state.q_rad")
        arms = state.get("arms")
        if isinstance(arms, Mapping):
            left = arms.get("left")
            if isinstance(left, Mapping) and "q_rad" in left:
                return _require_finite_seven(left["q_rad"], "arms.left.q_rad")
        raise ValueError("state mapping must contain q_rad or arms.left.q_rad")
    return _require_finite_seven(state, "q_rad")


def load_wrist_path(path: Path | str) -> dict[str, Any]:
    doc = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(doc, dict):
        raise ValueError("wrist-path must be a JSON object")
    return doc


def flatten_path_points(wrist_path: Mapping[str, Any]) -> list[dict[str, Any]]:
    if wrist_path.get("schema_version") != "wrist-path-0.1":
        raise ValueError("schema_version must be wrist-path-0.1")
    if wrist_path.get("side") != "left":
        raise ValueError("only left-arm wrist-path is supported")
    names = tuple(wrist_path.get("joint_names") or ())
    if names != JOINT_NAMES:
        raise ValueError("joint_names must be J1..J7")
    segments = wrist_path.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError("wrist-path requires non-empty segments")
    flat: list[dict[str, Any]] = []
    t_offset = 0.0
    for si, seg in enumerate(segments):
        if not isinstance(seg, Mapping):
            raise ValueError(f"segment[{si}] invalid")
        points = seg.get("points")
        if not isinstance(points, list) or not points:
            raise ValueError(f"segment[{si}] requires points")
        seg_t0 = float(points[0]["time_from_start_s"])
        for pi, pt in enumerate(points):
            q = _require_finite_seven(pt["q_rad"], f"segment[{si}].points[{pi}].q_rad")
            t_local = float(pt["time_from_start_s"])
            if pi > 0 and t_local <= float(points[pi - 1]["time_from_start_s"]):
                raise ValueError(f"segment[{si}] times must be strictly increasing")
            # Skip duplicate junction at segment starts after the first segment.
            if si > 0 and pi == 0:
                continue
            flat.append(
                {
                    "segment_index": si,
                    "segment_from": seg.get("from"),
                    "segment_to": seg.get("to"),
                    "point_index": pi,
                    "time_from_start_s": t_offset + (t_local - seg_t0),
                    "q_rad": list(q),
                }
            )
        t_offset = float(flat[-1]["time_from_start_s"])
    if not flat:
        raise ValueError("flattened path is empty")
    return flat


def fk_l8_translation_m(
    q_rad: Sequence[float],
    *,
    urdf_path: Path | str,
) -> tuple[float, float, float]:
    q = _require_finite_seven(q_rad, "fk q_rad")
    positions = {URDF_JOINTS[i]: q[i] for i in range(7)}
    pose, _report = urdf_forward_kinematics(
        Path(urdf_path),
        positions,
        base_frame=PARENT_FRAME,
        tip_frame=CHILD_FRAME,
    )
    t = pose.matrix[:3, 3]
    return (float(t[0]), float(t[1]), float(t[2]))


def _dist_m(a: Sequence[float], b: Sequence[float]) -> float:
    return math.sqrt(sum((float(a[i]) - float(b[i])) ** 2 for i in range(3)))


def validate_path_static(
    wrist_path: Mapping[str, Any],
    *,
    path_file: Path | str | None = None,
    expected_sha256_lf: str | None = None,
    urdf_path: Path | str | None = None,
) -> dict[str, Any]:
    blocked: list[str] = []
    notes: list[str] = []
    flat = flatten_path_points(wrist_path)

    sha_lf = file_sha256_lf(path_file) if path_file is not None else None
    if expected_sha256_lf:
        if sha_lf is None:
            blocked.append("expected_sha256_lf_requires_path_file")
        elif sha_lf != expected_sha256_lf:
            blocked.append("path_sha256_lf_mismatch")

    urdf = Path(urdf_path) if urdf_path is not None else LOCKED_URDF_REL
    # Lock digest is Git/LF bytes; normalize CRLF so Windows checkouts still match.
    digest = file_sha256_lf(urdf)
    if digest != LOCKED_URDF_SHA256:
        blocked.append("locked_urdf_sha256_mismatch")
    path_urdf = wrist_path.get("urdf_sha256")
    if path_urdf and path_urdf != LOCKED_URDF_SHA256:
        blocked.append("path_urdf_sha256_mismatch")

    audit = wrist_path.get("joint_audit") or {}
    if audit.get("J6") != "sdk_report_not_audited" or audit.get("J7") != "sdk_report_not_audited":
        blocked.append("j6_j7_must_remain_sdk_report_not_audited")
    prov = wrist_path.get("seed_provenance") or {}
    for key in ("grasp_ready", "place_ready"):
        row = prov.get(key)
        if row is not None and list(row) != list(SEED_PROVENANCE_DEFAULT):
            blocked.append(f"seed_provenance_{key}_unexpected")

    j2_vals = [float(pt["q_rad"][1]) for pt in flat]
    j2_min = min(j2_vals)
    if j2_min < J2_MIN_RAD:
        blocked.append("j2_below_minus_0_07")

    # Path evidence flags must stay false in-repo; player does not mutate them.
    for flag in ("executable", "motion_enabled", "control_ready"):
        if wrist_path.get(flag) is True:
            notes.append(f"path_file_{flag}_is_true_but_player_will_not_treat_as_live_permit")

    # Cartesian speed implied by path timestamps (offline check / stretch plan).
    tip0 = fk_l8_translation_m(flat[0]["q_rad"], urdf_path=urdf)
    tips = [tip0]
    max_implied = 0.0
    for i in range(1, len(flat)):
        tip = fk_l8_translation_m(flat[i]["q_rad"], urdf_path=urdf)
        tips.append(tip)
        dt = float(flat[i]["time_from_start_s"]) - float(flat[i - 1]["time_from_start_s"])
        d = _dist_m(tips[i - 1], tip)
        if dt > 1e-12:
            max_implied = max(max_implied, d / dt)
        elif d > 1e-9:
            blocked.append("zero_dt_nonzero_cartesian_step")

    return {
        "ok": not blocked,
        "blocked_by": blocked,
        "notes": notes,
        "path_sha256_lf": sha_lf,
        "expected_sha256_lf": expected_sha256_lf,
        "urdf_sha256": digest,
        "point_count": len(flat),
        "segment_count": len(wrist_path.get("segments") or []),
        "j2_min_rad": j2_min,
        "j2_limit_rad": J2_MIN_RAD,
        "max_implied_tcp_speed_m_s": max_implied,
        "max_tcp_speed_m_s": MAX_TCP_SPEED_M_S,
        "speed_stretch_required": bool(max_implied > MAX_TCP_SPEED_M_S + 1e-12),
        "grasp_ready_tip_m": list(tip0),
        "path_flags": {
            "executable": bool(wrist_path.get("executable")),
            "motion_enabled": bool(wrist_path.get("motion_enabled")),
            "control_ready": bool(wrist_path.get("control_ready")),
        },
        "joint_audit": {
            "J6": "sdk_report_not_audited",
            "J7": "sdk_report_not_audited",
        },
        "flattened_points": flat,
        "tip_translations_m": [list(t) for t in tips],
    }


def precheck_start_pose(
    current_q_rad: Sequence[float],
    *,
    grasp_ready_tip_m: Sequence[float],
    urdf_path: Path | str,
    arrival_max_m: float = ARRIVAL_MAX_M,
) -> dict[str, Any]:
    q = _require_finite_seven(current_q_rad, "current_q_rad")
    tip = fk_l8_translation_m(q, urdf_path=urdf_path)
    err = _dist_m(tip, grasp_ready_tip_m)
    ok = err <= float(arrival_max_m) + 1e-12
    return {
        "ok": ok,
        "current_tip_m": list(tip),
        "grasp_ready_tip_m": [float(x) for x in grasp_ready_tip_m],
        "error_m": err,
        "arrival_max_m": float(arrival_max_m),
        "reason": None if ok else "current_L8_farther_than_10mm_from_grasp_ready",
        "approach_path_invented": False,
    }


def evaluate_live_authorization(
    *,
    enable_live_motion: bool,
    authorization_ref: str | None,
) -> dict[str, Any]:
    blocked: list[str] = []
    if not enable_live_motion:
        blocked.append("missing_enable_live_motion")
    ref = (authorization_ref or "").strip()
    if not ref:
        blocked.append("missing_authorization_ref")
    return {
        "live_motion_requested": bool(enable_live_motion),
        "authorization_ref": ref or None,
        "live_dispatch_allowed": not blocked,
        "blocked_by": blocked,
        "default_motion_enabled": False,
        "opens_can_without_both_gates": False,
    }


def _segment_durations_speed_limited(
    flat: Sequence[Mapping[str, Any]],
    tips: Sequence[Sequence[float]],
    *,
    max_tcp_speed_m_s: float = MAX_TCP_SPEED_M_S,
) -> list[float]:
    """Per-step durations so consecutive TCP motion stays ≤ speed cap."""
    out: list[float] = []
    for i in range(1, len(flat)):
        d = _dist_m(tips[i - 1], tips[i])
        path_dt = float(flat[i]["time_from_start_s"]) - float(flat[i - 1]["time_from_start_s"])
        need = 0.0 if d <= 1e-12 else d / float(max_tcp_speed_m_s)
        out.append(max(path_dt, need))
    return out


def play_wrist_path(
    *,
    path_file: Path | str,
    expected_sha256_lf: str | None = None,
    urdf_path: Path | str | None = None,
    current_q_rad: Sequence[float] | None = None,
    assume_at_path_start: bool = False,
    enable_live_motion: bool = False,
    authorization_ref: str | None = None,
    arm: CoordinatedSevenAxisArm | None = None,
    arm_factory: Callable[[], CoordinatedSevenAxisArm] | None = None,
    max_tcp_speed_m_s: float = MAX_TCP_SPEED_M_S,
    arrival_max_m: float = ARRIVAL_MAX_M,
) -> dict[str, Any]:
    """Load / precheck / optionally dispatch a left wrist-path.

    Default is dry-run: no CAN, no enable, no motion. Live requires both
    ``enable_live_motion`` and non-empty ``authorization_ref``, plus an injected
    coordinated seven-axis backend (tests) or ``arm_factory`` invoked only after
    static validation and authorization gates pass.
    """
    path_file = Path(path_file)
    urdf = Path(urdf_path) if urdf_path is not None else LOCKED_URDF_REL
    wrist_path = load_wrist_path(path_file)
    static = validate_path_static(
        wrist_path,
        path_file=path_file,
        expected_sha256_lf=expected_sha256_lf,
        urdf_path=urdf,
    )
    live_gate = evaluate_live_authorization(
        enable_live_motion=enable_live_motion,
        authorization_ref=authorization_ref,
    )

    report: dict[str, Any] = {
        "schema_version": SCHEMA,
        "path_file": str(path_file.as_posix()),
        "motion_backend_kind": MOTION_BACKEND_KIND,
        "forbidden_backends": list(FORBIDDEN_BACKENDS),
        "finger_commands_issued": False,
        "hand_touched": False,
        "right_arm_commands_issued": False,
        "rest_issued": False,
        "single_joint_moves": False,
        "path_file_mutated": False,
        "joint_audit": {"J6": "sdk_report_not_audited", "J7": "sdk_report_not_audited"},
        "limits": {
            "max_tcp_speed_m_s": float(max_tcp_speed_m_s),
            "cartesian_arrival_max_m": float(arrival_max_m),
            "j2_min_rad": J2_MIN_RAD,
        },
        "static_validation": {
            k: v
            for k, v in static.items()
            if k not in ("flattened_points", "tip_translations_m")
        },
        "live_authorization": live_gate,
        "motion_started": False,
        "completed": False,
        "verdict": "UNKNOWN",
        "segment_end_errors_m": None,
        "j2_min_rad_observed": None,
        "actual_speed_cap_m_s": None,
        "moves_dispatched": 0,
    }

    if not static["ok"]:
        report["verdict"] = "REFUSE_STATIC_VALIDATION"
        report["blocked_by"] = list(static["blocked_by"])
        return report

    # Live gate fails closed before any current-q read or CAN open.
    if enable_live_motion and not live_gate["live_dispatch_allowed"]:
        report["verdict"] = "REFUSE_LIVE_AUTHORIZATION"
        report["blocked_by"] = list(live_gate["blocked_by"])
        report["notes"] = [
            "Live requires both --enable-live-motion and non-empty --authorization-ref.",
            "Neither CAN nor motor enable is opened when either gate is missing.",
        ]
        return report

    flat = static["flattened_points"]
    tips = static["tip_translations_m"]
    grasp_tip = static["grasp_ready_tip_m"]

    q_now: tuple[float, ...] | None = None
    q_source: str | None = None
    if current_q_rad is not None:
        q_now = _require_finite_seven(current_q_rad, "current_q_rad")
        q_source = "explicit"
    elif assume_at_path_start:
        q_now = _require_finite_seven(flat[0]["q_rad"], "path_start_q")
        q_source = "assume_at_path_start"

    if q_now is None and not live_gate["live_dispatch_allowed"]:
        report["verdict"] = "DRY_RUN_NEED_CURRENT_Q"
        report["blocked_by"] = ["missing_current_q_rad_for_precheck"]
        report["notes"] = [
            "Pass --current-q-json or --assume-at-path-start for dry-run precheck.",
            "Readonly host_monitor may return null J6/J7; refuse inventing wrist angles.",
        ]
        return report

    # Dry-run with known q: finish start gate without opening hardware.
    if q_now is not None and not live_gate["live_dispatch_allowed"]:
        start = precheck_start_pose(
            q_now,
            grasp_ready_tip_m=grasp_tip,
            urdf_path=urdf,
            arrival_max_m=arrival_max_m,
        )
        report["start_precheck"] = {**start, "q_source": q_source}
        if not start["ok"]:
            report["verdict"] = "REFUSE_START_POSE"
            report["blocked_by"] = [start["reason"]]
            return report
        durations = _segment_durations_speed_limited(
            flat, tips, max_tcp_speed_m_s=max_tcp_speed_m_s
        )
        report["planned_step_count"] = len(durations)
        report["planned_total_duration_s"] = float(sum(durations))
        report["actual_speed_cap_m_s"] = float(max_tcp_speed_m_s)
        report["verdict"] = "DRY_RUN_OK"
        report["completed"] = False
        report["motion_started"] = False
        report["notes"] = [
            "Dry-run only: path hash/static gates/start pose OK; no motion commanded.",
            f"Future live backend: {MOTION_BACKEND_KIND} (seven joints per call).",
            "Not host_monitor single-joint; not T1 short-combo; not MockArm replay.",
            "Finger/hand commands are structurally absent from this player.",
        ]
        report["dry_plan"] = {
            "points": len(flat),
            "first_q_rad": list(flat[0]["q_rad"]),
            "last_q_rad": list(flat[-1]["q_rad"]),
            "segment_ends": [
                {
                    "to": seg.get("to"),
                    "q_rad": list((seg.get("points") or [])[-1]["q_rad"]),
                }
                for seg in (wrist_path.get("segments") or [])
            ],
        }
        return report

    # Live path: open coordinated backend only after static + auth gates.
    owns_arm = False
    if arm is None and arm_factory is not None:
        arm = arm_factory()
        owns_arm = True
    if arm is None:
        report["verdict"] = "REFUSE_NO_ARM_BACKEND"
        report["blocked_by"] = ["live_authorized_but_no_coordinated_seven_axis_backend"]
        report["notes"] = [
            "Construct linkerbot P7 move_j backend only after both live gates pass.",
        ]
        return report

    if arm.backend_kind in FORBIDDEN_BACKENDS or "single_joint" in arm.backend_kind:
        report["verdict"] = "REFUSE_FORBIDDEN_BACKEND"
        report["blocked_by"] = [f"forbidden_backend:{arm.backend_kind}"]
        if owns_arm:
            arm.close()
        return report

    try:
        if q_now is None:
            q_now = arm.read_q_rad()
            q_source = f"backend:{arm.backend_kind}"
    except Exception as exc:
        report["verdict"] = "REFUSE_CURRENT_Q"
        report["blocked_by"] = [f"backend_read_q_failed:{exc}"]
        if owns_arm:
            arm.close()
        return report

    start = precheck_start_pose(
        q_now,
        grasp_ready_tip_m=grasp_tip,
        urdf_path=urdf,
        arrival_max_m=arrival_max_m,
    )
    report["start_precheck"] = {**start, "q_source": q_source}
    if not start["ok"]:
        report["verdict"] = "REFUSE_START_POSE"
        report["blocked_by"] = [start["reason"]]
        if owns_arm:
            arm.close()
        return report

    durations = _segment_durations_speed_limited(
        flat, tips, max_tcp_speed_m_s=max_tcp_speed_m_s
    )
    report["planned_step_count"] = len(durations)
    report["planned_total_duration_s"] = float(sum(durations))
    report["actual_speed_cap_m_s"] = float(max_tcp_speed_m_s)

    # Live coordinated playback.
    try:
        report["motion_started"] = True
        j2_min_obs = float(q_now[1])
        end_errors: list[dict[str, Any]] = []
        last_index_by_segment: dict[int, int] = {}
        for i, pt in enumerate(flat):
            last_index_by_segment[int(pt["segment_index"])] = i

        for i, pt in enumerate(flat):
            q = _require_finite_seven(pt["q_rad"], "path_point")
            j2_min_obs = min(j2_min_obs, float(q[1]))
            if float(q[1]) < J2_MIN_RAD:
                report["verdict"] = "ABORT_J2_LIMIT"
                report["blocked_by"] = ["j2_below_minus_0_07_during_play"]
                report["j2_min_rad_observed"] = j2_min_obs
                return report
            if i == 0:
                # Already at start within gate; skip no-op move.
                continue
            arm.move_j_seven(q, duration_s=durations[i - 1])
            report["moves_dispatched"] = int(report["moves_dispatched"]) + 1
            measured = arm.read_q_rad()
            j2_min_obs = min(j2_min_obs, float(measured[1]))
            tip_now = fk_l8_translation_m(measured, urdf_path=urdf)
            tip_goal = tips[i]
            err = _dist_m(tip_now, tip_goal)
            if err > float(arrival_max_m) + 1e-9:
                report["verdict"] = "ABORT_ARRIVAL"
                report["blocked_by"] = ["arrival_error_exceeded_10mm"]
                report["abort_point_index"] = i
                report["abort_error_m"] = err
                report["j2_min_rad_observed"] = j2_min_obs
                return report
            if last_index_by_segment.get(int(pt["segment_index"])) == i:
                end_errors.append(
                    {
                        "from": pt.get("segment_from"),
                        "to": pt.get("segment_to"),
                        "error_m": err,
                        "tip_m": list(tip_now),
                        "goal_tip_m": list(tip_goal),
                    }
                )

        report["completed"] = True
        report["verdict"] = "LIVE_PLAY_OK"
        report["segment_end_errors_m"] = end_errors
        report["j2_min_rad_observed"] = j2_min_obs
        report["finger_commands_issued"] = False
        if isinstance(arm, RecordingSevenAxisArm):
            report["recording"] = {
                "moves": len(arm.moves),
                "all_moves_seven_axis": all(
                    m.get("joint_count") == 7 and m.get("single_joint") is False
                    for m in arm.moves
                ),
                "hand_commands": list(arm.hand_commands),
                "rest_commands": list(arm.rest_commands),
                "right_arm_commands": list(arm.right_arm_commands),
            }
        return report
    finally:
        if owns_arm and arm is not None:
            try:
                arm.close()
            except Exception:
                pass


def build_linkerbot_p7_move_j_backend(
    *,
    side: str = "left",
    interface_name: str = "can2",
    linkerbot_src: str | None = None,
) -> CoordinatedSevenAxisArm:
    """Lazy P7 wrapper. Call only after live authorization gates pass.

    Does not construct O6, does not call Rest, does not touch the right arm.
    Instantiating vendor ``P7`` may perform SDK-internal V2 mode checks; this
    factory is intentionally unreachable from the default dry-run path.
    """
    if linkerbot_src:
        import sys

        src = str(Path(linkerbot_src))
        if src not in sys.path:
            sys.path.insert(0, src)
    from linkerbot import P7  # type: ignore

    class _P7MoveJBackend:
        backend_kind = MOTION_BACKEND_KIND

        def __init__(self) -> None:
            self._arm = P7(side=side, interface_name=interface_name)

        def read_q_rad(self) -> tuple[float, float, float, float, float, float, float]:
            angles = self._arm.get_angles()
            return _require_finite_seven(list(angles), "P7.get_angles")

        def move_j_seven(
            self,
            q_rad: Sequence[float],
            *,
            duration_s: float | None = None,
        ) -> None:
            q = _require_finite_seven(q_rad, "P7.move_j")
            # Coordinated seven-axis command — one SDK call, not seven single-joint MOVEs.
            if duration_s is not None and hasattr(self._arm, "move_j"):
                t0 = time.monotonic()
                self._arm.move_j(list(q))
                # Best-effort pace to respect TCP speed budget if SDK returns early.
                remain = float(duration_s) - (time.monotonic() - t0)
                if remain > 0:
                    time.sleep(remain)
            else:
                self._arm.move_j(list(q))

        def close(self) -> None:
            close = getattr(self._arm, "close", None)
            if callable(close):
                close()

    return _P7MoveJBackend()
