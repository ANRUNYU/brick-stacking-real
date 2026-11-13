"""Reusable, explicitly gated robot motion routines."""

from .celebration import (
    MAX_LOOPS,
    RETURN_TOLERANCE_RAD,
    CelebrationPlan,
    MotionSegment,
    build_celebration_plan,
    run_celebration,
    validate_loop_count,
)

__all__ = [
    "MAX_LOOPS",
    "RETURN_TOLERANCE_RAD",
    "CelebrationPlan",
    "MotionSegment",
    "build_celebration_plan",
    "run_celebration",
    "validate_loop_count",
]
