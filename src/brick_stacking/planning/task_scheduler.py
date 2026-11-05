from brick_stacking.models.scene_state import BlockLocation


def choose_task(scene, manager):
    """Single-arm V1 policy. Snapshot quality/time is checked by SafetyGate."""
    for slot in manager.ready_slots():
        blocks = [b for b in scene.blocks if b.location == BlockLocation.SUPPLY and b.visible
                  and not b.ambiguous and b.color == slot.required_color and b.frame_id == slot.frame_id]
        if blocks:
            return min(blocks, key=lambda b: b.object_id), slot
    return None
