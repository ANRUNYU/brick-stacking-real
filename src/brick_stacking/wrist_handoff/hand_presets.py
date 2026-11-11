"""O6 GraspPreset pack for Line H (preshape / close / open). Not sent to line P."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from brick_stacking.wrist_handoff.constants import HAND_CHANNEL_NAMES


def _six_percent(values: Sequence[float], *, label: str) -> list[float]:
    if len(values) != 6:
        raise ValueError(f"{label} requires six channels")
    out = [float(v) for v in values]
    if any(not (0.0 <= v <= 100.0) for v in out):
        raise ValueError(f"{label} percent values must be in [0, 100]")
    return out


def build_hand_preset(
    *,
    role: str,
    preset_version: str,
    name: str,
    percent: Sequence[float],
    speed_percent: Sequence[float] | None = None,
    geometry_assumptions: Sequence[str] = (),
    applicable_objects: Sequence[str] = ("50mm_cube",),
) -> dict[str, Any]:
    if role not in ("left", "right"):
        raise ValueError("role must be left or right")
    if not preset_version.strip() or not name.strip():
        raise ValueError("preset_version and name required")
    speed = speed_percent if speed_percent is not None else (20.0,) * 6
    return {
        "role": role,
        "name": name,
        "preset_version": preset_version,
        "channel_names": list(HAND_CHANNEL_NAMES),
        "position": {"unit": "percent", "values": _six_percent(percent, label=name)},
        "speed": {"unit": "percent", "values": _six_percent(speed, label=f"{name}.speed")},
        "geometry_assumptions": list(geometry_assumptions),
        "applicable_objects": list(applicable_objects),
    }


def build_hand_preset_pack(
    *,
    role: str,
    pack_version: str,
    open_percent: Sequence[float],
    preshape_percent: Sequence[float],
    close_percent: Sequence[float],
    speed_percent: Sequence[float] | None = None,
    notes: Sequence[str] = (),
) -> dict[str, Any]:
    """Three-finger pack: open / preshape / close. Does not reuse C49 two-finger."""
    if not pack_version.strip():
        raise ValueError("pack_version required")
    geom = (
        "three_finger_thumb_index_middle",
        "ring_pinky_explicit_percent_required",
        "not_c49_two_finger",
    )
    return {
        "schema_version": "hand-preset-pack-0.1",
        "pack_version": pack_version,
        "role": role,
        "finger_strategy": "three_finger",
        "approved_for_motion": False,
        "notes": list(notes),
        "presets": {
            "open": build_hand_preset(
                role=role,
                preset_version=f"{pack_version}/open",
                name="open",
                percent=open_percent,
                speed_percent=speed_percent,
                geometry_assumptions=geom,
            ),
            "preshape": build_hand_preset(
                role=role,
                preset_version=f"{pack_version}/preshape",
                name="preshape",
                percent=preshape_percent,
                speed_percent=speed_percent,
                geometry_assumptions=geom,
            ),
            "close": build_hand_preset(
                role=role,
                preset_version=f"{pack_version}/close",
                name="close",
                percent=close_percent,
                speed_percent=speed_percent,
                geometry_assumptions=geom,
            ),
        },
    }


def require_pack(pack: Mapping[str, Any]) -> dict[str, Any]:
    if pack.get("schema_version") != "hand-preset-pack-0.1":
        raise ValueError("hand-preset-pack-0.1 required")
    for key in ("open", "preshape", "close"):
        if key not in (pack.get("presets") or {}):
            raise ValueError(f"missing preset {key}")
    return dict(pack)
