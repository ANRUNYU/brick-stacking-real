"""Parameterised target geometry; never an arm or wrist target."""
import math
from brick_stacking.models.scene_state import Slot


def build_stacking_slots(*, edge_m, layers, colors_by_layer, center_xy_m, yaw_rad, frame_id, gap_m=0.0):
    if not math.isfinite(edge_m) or edge_m <= 0 or not math.isfinite(yaw_rad) or not frame_id:
        raise ValueError("finite edge, heading and reference frame required")
    if len(center_xy_m) != 2 or not all(map(math.isfinite, center_xy_m)):
        raise ValueError("finite target center required")
    if not layers or len(layers) != len(colors_by_layer) or any(type(n) is not int or n < 1 for n in layers):
        raise ValueError("positive layer counts and colors required")
    if any(a - b != 1 for a, b in zip(layers, layers[1:])):
        raise ValueError("this model supports centered decreasing-by-one layers only")
    if any(c not in {"red", "yellow", "blue", "green"} for c in colors_by_layer):
        raise ValueError("explicit four-color labels required")
    if not math.isfinite(gap_m) or gap_m < 0 or gap_m >= edge_m:
        raise ValueError("finite gap must preserve positive overlap with both supports")
    slots, previous = [], []
    for layer, count in enumerate(layers):
        current = []
        for column in range(count):
            slot_id = f"L{layer}_{column}"
            x = (column - (count - 1) / 2) * (edge_m + gap_m)
            center = (center_xy_m[0] + math.cos(yaw_rad) * x,
                      center_xy_m[1] + math.sin(yaw_rad) * x, (layer + .5) * edge_m)
            supports = () if layer == 0 else (previous[column], previous[column + 1])
            slots.append(Slot(slot_id, layer, colors_by_layer[layer], center, frame_id, supports))
            current.append(slot_id)
        previous = current
    return tuple(slots)
