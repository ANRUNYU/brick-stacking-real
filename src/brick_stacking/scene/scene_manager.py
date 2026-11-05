"""Reservations commit only after fresh verification; no inference from SDK return."""
from brick_stacking.models.scene_state import SlotState


class SceneManager:
    def __init__(self, slots):
        self.slots = {s.slot_id: s for s in slots}
        if len(self.slots) != len(slots):
            raise ValueError("duplicate slot IDs")
        seen = set()
        for slot in slots:
            if any(s not in seen for s in slot.supports):
                raise ValueError("support graph must be acyclic and topologically ordered")
            seen.add(slot.slot_id)
        self.states = {key: SlotState.EMPTY for key in self.slots}
        self.occupants = {}
        self.reservations = {}

    def ready_slots(self):
        return tuple(s for key, s in self.slots.items() if self.states[key] == SlotState.EMPTY
                     and all(self.states[k] == SlotState.PLACED_VERIFIED for k in s.supports))

    def reserve(self, slot_id, object_id):
        if slot_id not in {s.slot_id for s in self.ready_slots()}:
            raise ValueError("slot unavailable or support unverified")
        if object_id in self.reservations.values() or object_id in self.occupants.values():
            raise ValueError("block already allocated")
        self.reservations[slot_id] = object_id
        self.states[slot_id] = SlotState.RESERVED

    def mark_unverified(self, slot_id):
        if slot_id not in self.reservations:
            raise ValueError("unreserved slot")
        self.states[slot_id] = SlotState.UNVERIFIED

    def commit_verified(self, slot_id, object_id):
        if self.states[slot_id] != SlotState.UNVERIFIED or self.reservations.get(slot_id) != object_id:
            raise ValueError("verification does not match pending transaction")
        self.states[slot_id] = SlotState.PLACED_VERIFIED
        self.occupants[slot_id] = self.reservations.pop(slot_id)

    def cancel_before_pick(self, slot_id):
        if self.states[slot_id] != SlotState.RESERVED:
            raise ValueError("cannot erase uncertain post-pick occupancy")
        self.reservations.pop(slot_id)
        self.states[slot_id] = SlotState.EMPTY
