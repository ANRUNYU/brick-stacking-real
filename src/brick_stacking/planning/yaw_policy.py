"""Explicit yaw policies for pre-grasp / shadow Inspection.

Unmarked resting cubes are orientation-equivalent modulo pi/2. That is not a
MEASURED ErrorBound: keep yaw status UNKNOWN and declare a policy when grasp-
approach may proceed without a forged angle.
"""
from __future__ import annotations

import math
from typing import Any

YAW_POLICY_SYMMETRIC_90_UNBOUNDED = "symmetric_90_unbounded"
SYMMETRIC_90_PERIOD_RAD = math.pi / 2
_PERIOD_TOL = 1e-9


def normalize_yaw_policy(raw: Any) -> dict[str, Any] | None:
    """Return a validated policy dict, or None if absent/invalid."""
    if not isinstance(raw, dict):
        return None
    policy_id = raw.get("id") or raw.get("policy_id")
    if policy_id != YAW_POLICY_SYMMETRIC_90_UNBOUNDED:
        return None
    if raw.get("do_not_forge_measured_pass") is False:
        return None
    period = raw.get("symmetry_period_rad")
    if type(period) not in (int, float) or not math.isfinite(float(period)):
        return None
    if abs(float(period) - SYMMETRIC_90_PERIOD_RAD) > _PERIOD_TOL:
        return None
    return {
        "id": YAW_POLICY_SYMMETRIC_90_UNBOUNDED,
        "symmetry_period_rad": float(period),
        "status": "UNKNOWN",
        "reason": raw.get("reason") or "90deg_cube_symmetry_no_bounded_measurement",
        "do_not_forge_measured_pass": True,
        "applies_to": list(
            raw.get("applies_to")
            or (
                "pre_grasp_grasp_approach",
                "shadow_inspection",
            )
        ),
    }


def yaw_unknown_allowed_by_policy(yaw_metric: dict | None, yaw_policy: Any) -> bool:
    """True when UNKNOWN yaw may skip ERROR_BOUND_UNKNOWN under explicit policy."""
    metric = yaw_metric or {}
    if metric.get("status") == "MEASURED":
        return False
    if metric.get("status") != "UNKNOWN":
        return False
    # Refuse any attempt to smuggle a numeric angle through the UNKNOWN path.
    if metric.get("value") is not None or metric.get("bound") is not None:
        return False
    return normalize_yaw_policy(yaw_policy) is not None
