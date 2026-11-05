"""Position-only offline evidence checks. Orientation/contact remain unverified."""
import math
from brick_stacking.models.scene_state import BlockLocation


def verify_placement(snapshot, block_id, slot, *, xy_tolerance_m, z_tolerance_m):
    for tolerance in (xy_tolerance_m, z_tolerance_m):
        if not math.isfinite(tolerance) or tolerance <= 0:
            raise ValueError("positive finite tolerances required")
    block = next((b for b in snapshot.blocks if b.object_id == block_id), None)
    if block is None or not block.visible or block.ambiguous or not snapshot.hand_clear:
        return "UNOBSERVABLE"
    if block.frame_id != slot.frame_id or block.color != slot.required_color or block.location != BlockLocation.PLACED:
        return "FAIL"
    dx, dy, dz = (a - b for a, b in zip(block.center_m, slot.center_m))
    return "PASS" if math.hypot(dx, dy) <= xy_tolerance_m and abs(dz) <= z_tolerance_m else "FAIL"


def verify_stability(snapshots, allocations, slots, *, minimum_span_s, spread_m, xy_tolerance_m, z_tolerance_m):
    if len(snapshots) < 2 or minimum_span_s <= 0 or spread_m <= 0:
        return False
    first = snapshots[0]
    if (any(s.epoch != first.epoch or s.clock_domain != first.clock_domain for s in snapshots)
            or len({s.observation_id for s in snapshots}) != len(snapshots)
            or any(b.stamp_s <= a.stamp_s for a, b in zip(snapshots, snapshots[1:]))
            or snapshots[-1].stamp_s - first.stamp_s < minimum_span_s):
        return False
    for slot_id, object_id in allocations.items():
        points = []
        for snapshot in snapshots:
            if verify_placement(snapshot, object_id, slots[slot_id], xy_tolerance_m=xy_tolerance_m,
                                z_tolerance_m=z_tolerance_m) != "PASS":
                return False
            points.append(next(b.center_m for b in snapshot.blocks if b.object_id == object_id))
        if any(math.dist(a, b) > spread_m for a in points for b in points):
            return False
    return bool(allocations)
