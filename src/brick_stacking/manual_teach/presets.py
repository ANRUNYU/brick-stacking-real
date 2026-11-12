"""Operator-locked left O6 poses from the 2026-11-13 teach panel.

Channel order: thumb_flex, thumb_abd, index, middle, ring, pinky. Unit: percent.
0 is fully flexed, 100 is open, matching the panel scale 「0 弯到底 / 100 张开」.

Grasp replaces the previous close pose (about 60 / 32 / 60 / 56 / 0 / 0).
Release is the non-grasp pose: the panel 读数 in the operator screenshot.
Use release whenever the hand is not holding a block.
"""

from __future__ import annotations

HAND_CHANNELS = (
    "thumb_flex",
    "thumb_abd",
    "index",
    "middle",
    "ring",
    "pinky",
)
HAND_LABELS_ZH = ("拇指弯", "拇指张", "食指", "中指", "无名指", "小指")
ARM_JOINTS = ("J1", "J2", "J3", "J4", "J5", "J6", "J7")

# Readings the operator called out for grasp.
GRASP_PERCENT = (40.8, 23.9, 76.5, 72.9, 0.0, 0.0)
# Screenshot 读数 for the pose used whenever not grasping.
RELEASE_PERCENT = (83.5, 23.9, 84.3, 84.3, 0.0, 0.0)

DEFAULT_SPEED_PERCENT = 12.0
MAX_SPEED_PERCENT = 15.0
SAMPLE_HZ = 100


def percent_to_raw_u8(percent: float) -> int:
    """Map a teach-panel percent to the 0–255 raw byte.

    Live O6 feedback is ``raw_u8 / 255 * 100``. ``set_raw_angles`` uses that
    same 0–255 byte. ``set_angles`` takes the percent directly.
    """
    raw = int(round(float(percent) * 255.0 / 100.0))
    if raw < 0 or raw > 255:
        raise ValueError("raw byte must be in [0, 255]")
    return raw


def raw_u8_to_percent(raw: int) -> float:
    """Inverse of :func:`percent_to_raw_u8` for one feedback byte."""
    if type(raw) is not int or not 0 <= raw <= 255:
        raise ValueError("raw byte must be an int in [0, 255]")
    return raw * 100.0 / 255.0


def as_percent_list(values: tuple[float, ...] | list[float]) -> list[float]:
    if len(values) != 6:
        raise ValueError("hand pose requires six channels")
    out = [float(v) for v in values]
    if any(not (0.0 <= v <= 100.0) for v in out):
        raise ValueError("hand percent must be in [0, 100]")
    return out
