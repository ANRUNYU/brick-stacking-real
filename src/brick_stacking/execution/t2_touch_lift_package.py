"""T2 touch → close → micro-lift safety package (default non-executable).

T2 (THREE_TRACK §3.5): descend to contact → hand close → vertical micro-lift.
Does not raise control_ready. Live motion requires an explicit live runner and
field placement; this module defines gated stages and mock/dry-run only.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


SCHEMA = "m-t2-touch-lift-package-0.1"


class T2Stage(str, Enum):
    PRECHECK = "PRECHECK"
    HOVER = "HOVER"
    DESCEND = "DESCEND"
    CLOSE = "CLOSE"
    MICRO_LIFT = "MICRO_LIFT"
    HOLD_CHECK = "HOLD_CHECK"
    DONE = "DONE"
    SAFE_HALT = "SAFE_HALT"


STAGE_ORDER = (
    T2Stage.PRECHECK,
    T2Stage.HOVER,
    T2Stage.DESCEND,
    T2Stage.CLOSE,
    T2Stage.MICRO_LIFT,
    T2Stage.HOLD_CHECK,
    T2Stage.DONE,
)


@dataclass(frozen=True)
class T2Limits:
    """Conservative Cartesian bounds for T2 (meters)."""

    descend_max_m: float = 0.03
    micro_lift_min_m: float = 0.03
    approach_height_min_m: float = 0.08
    max_tcp_speed_m_s: float = 0.05
    require_empty_table_except_target: bool = True
    require_explicit_live_motion: bool = True
    prefer_sdk_move_l: bool = True


@dataclass
class T2PackageResult:
    stage: T2Stage
    reason: str | None = None
    stages: list[str] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    live_motion_allowed: bool = False
    control_ready: bool = False
    executable: bool = False
    payload: dict[str, Any] = field(default_factory=dict)


def build_t2_package(
    next_step: Callable[[T2Stage], T2Stage | tuple[T2Stage, str]] | None = None,
    *,
    limits: T2Limits | None = None,
    mock: bool = True,
    live_motion: bool = False,
    block_present_attested: bool = False,
    clear_workspace_attested: bool = False,
    e_stop_reachable_attested: bool = False,
) -> T2PackageResult:
    """Run T2 stage machine. Default mock=True never sends hardware commands."""
    lim = limits or T2Limits()
    events: list[dict[str, Any]] = []
    stages: list[str] = []

    def halt(reason: str) -> T2PackageResult:
        events.append({"stage": T2Stage.SAFE_HALT.value, "reason": reason})
        return T2PackageResult(
            stage=T2Stage.SAFE_HALT,
            reason=reason,
            stages=stages,
            events=events,
            live_motion_allowed=False,
            control_ready=False,
            executable=False,
            payload={"schema_version": SCHEMA, "limits": lim.__dict__, "mock": mock},
        )

    if lim.descend_max_m <= 0 or lim.micro_lift_min_m < 0.03:
        return halt("T2 limits refuse: descend_max_m>0 and micro_lift_min_m>=0.03 required")
    if lim.approach_height_min_m < 0.08:
        return halt("T2 limits refuse: approach_height_min_m must be >= 0.08")

    if not clear_workspace_attested or not e_stop_reachable_attested:
        return halt("T2 precheck: workspace clear + e-stop reachable attestations required")
    if not block_present_attested:
        return halt("T2 precheck: target block presence attestation required (no silent assume)")
    if live_motion and mock:
        return halt("T2 refuses live_motion=true together with mock=true")
    if live_motion:
        return halt(
            "T2 live path not auto-started here; use explicit live runner after "
            "field placement (prefer SDK move_l micro segments)"
        )

    for expected in STAGE_ORDER:
        stages.append(expected.value)
        if next_step is None:
            events.append({"stage": expected.value, "status": "MOCK_OK"})
            continue
        outcome = next_step(expected)
        if isinstance(outcome, tuple):
            nxt, reason = outcome
            if nxt == T2Stage.SAFE_HALT:
                return halt(reason)
            events.append({"stage": expected.value, "status": "OK", "detail": reason})
        elif outcome == T2Stage.SAFE_HALT:
            return halt(f"halt at {expected.value}")
        else:
            events.append({"stage": expected.value, "status": "OK"})

    return T2PackageResult(
        stage=T2Stage.DONE,
        reason="t2_mock_or_dry_stages_complete",
        stages=stages,
        events=events,
        live_motion_allowed=False,
        control_ready=False,
        executable=False,
        payload={
            "schema_version": SCHEMA,
            "limits": lim.__dict__,
            "mock": mock,
            "motion_stack_direction": "prefer_sdk_move_l_for_cartesian_micro",
            "notes": [
                "Not a live touch. Field: place one target block, attest, then live runner.",
                "control_ready remains false.",
            ],
        },
    )
