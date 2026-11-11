"""Inspect XML without loading meshes, installing SDKs or touching hardware."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping, Sequence
import xml.etree.ElementTree as ET

# Left P7 revolute chain used by joint-space dry-plan (J1..J7).
DEFAULT_LEFT_REVOLUTE_JOINTS: tuple[str, ...] = tuple(f"L{i}_Joint" for i in range(1, 8))
DEFAULT_EXEC_JOINT_NAMES: tuple[str, ...] = tuple(f"J{i}" for i in range(1, 8))


def inspect_urdf(path):
    root = ET.fromstring(Path(path).read_text(encoding="utf-8"))
    if root.tag != "robot":
        raise ValueError("not a URDF robot")
    joints = []
    for element in root.findall("joint"):
        limit, mimic = element.find("limit"), element.find("mimic")
        parent, child = element.find("parent"), element.find("child")
        joints.append({"name": element.get("name"), "type": element.get("type"),
            "parent": parent.get("link") if parent is not None else None,
            "child": child.get("link") if child is not None else None,
            "declared_limits": dict(limit.attrib) if limit is not None else None,
            "mimic": dict(mimic.attrib) if mimic is not None else None})
    return {"robot": root.get("name"), "link_count": len(root.findall("link")),
            "joints": joints, "hardware_match_verified": False,
            "notice": "Declared model geometry is not measured installation or certified hardware limits."}


def urdf_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def declared_revolute_limits(
    path: str | Path,
    *,
    joint_names: Sequence[str] = DEFAULT_LEFT_REVOLUTE_JOINTS,
) -> dict[str, Any]:
    """Extract ordered declared <limit> for named revolute joints.

    Returns kinematics-declared bounds only. Never claims hardware verification
    or Flash COM Theta equivalence.
    """
    audit = inspect_urdf(path)
    by_name = {j["name"]: j for j in audit["joints"] if j.get("name")}
    lower: list[float] = []
    upper: list[float] = []
    velocity: list[float] = []
    ordered_urdf: list[str] = []
    for name in joint_names:
        joint = by_name.get(name)
        if joint is None:
            raise ValueError(f"URDF missing joint {name}")
        if joint.get("type") != "revolute":
            raise ValueError(f"joint {name} must be revolute")
        limits = joint.get("declared_limits")
        if not isinstance(limits, Mapping) or "lower" not in limits or "upper" not in limits:
            raise ValueError(f"joint {name} missing declared lower/upper")
        lo = float(limits["lower"])
        hi = float(limits["upper"])
        if not (lo < hi):
            raise ValueError(f"joint {name} declared limits invalid")
        vel = float(limits["velocity"]) if limits.get("velocity") is not None else None
        if vel is None or vel <= 0:
            raise ValueError(f"joint {name} missing positive declared velocity")
        lower.append(lo)
        upper.append(hi)
        velocity.append(vel)
        ordered_urdf.append(name)
    path_obj = Path(path)
    raw = path_obj.read_text(encoding="utf-8")
    mesh_or_collision = ("<mesh" in raw) or ("<collision" in raw)
    return {
        "robot": audit.get("robot"),
        "urdf_path": str(path_obj),
        "urdf_sha256": urdf_sha256(path_obj),
        "urdf_joint_names": ordered_urdf,
        "joint_names": list(DEFAULT_EXEC_JOINT_NAMES[: len(ordered_urdf)]),
        "lower_rad": lower,
        "upper_rad": upper,
        "velocity_rad_s": velocity,
        "hardware_match_verified": False,
        "mesh_or_collision_present": mesh_or_collision,
        "notice": (
            "Declared URDF limits only; not Flash COM Theta; not verified "
            "left_wrist_theta_ranges; not H3."
        ),
    }


def target_within_declared_limits(
    joint_index_0: int,
    target_rad: float,
    *,
    lower_rad: Sequence[float],
    upper_rad: Sequence[float],
) -> bool:
    if joint_index_0 < 0 or joint_index_0 >= len(lower_rad):
        raise ValueError("joint_index_0 out of range")
    return float(lower_rad[joint_index_0]) <= float(target_rad) <= float(upper_rad[joint_index_0])
