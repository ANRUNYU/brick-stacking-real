"""Reservations commit only after fresh verification; no inference from SDK return."""
from graphlib import TopologicalSorter
from threading import RLock

from brick_stacking.models.scene_state import SlotState
from brick_stacking.scene.supply_tracker import SupplyTracker


class SceneManager:
    def __init__(self, slots, *, supply_match_distance_m=None):
        slots = tuple(slots)
        self.slots = {s.slot_id: s for s in slots}
        if len(self.slots) != len(slots):
            raise ValueError("duplicate slot IDs")
        graph = {slot.slot_id: slot.supports for slot in slots}
        if any(support not in graph for supports in graph.values() for support in supports):
            raise ValueError("support graph references an unknown slot")
        tuple(TopologicalSorter(graph).static_order())
        self._ordered_slots = tuple(sorted(slots, key=lambda slot: slot.layer))
        self.states = {key: SlotState.EMPTY for key in self.slots}
        self.occupants = {}
        self.reservations = {}
        self._lock = RLock()
        self._supply_tracker = (
            SupplyTracker(supply_match_distance_m) if supply_match_distance_m is not None else None
        )

    def update_supply(self, observation):
        """Associate one localized supply frame before passing it to the scheduler."""
        with self._lock:
            if self._supply_tracker is None:
                raise ValueError("supply association distance is not configured")
            return self._supply_tracker.update(observation, set(self.occupants.values()))

    def allocated_block_ids(self):
        with self._lock:
            return set(self.reservations.values()) | set(self.occupants.values())

    def ready_slots(self, *, lowest_pending_layer_only=False):
        with self._lock:
            slots = self._ordered_slots
            if lowest_pending_layer_only:
                layer = next((slot.layer for slot in slots
                              if self.states[slot.slot_id] != SlotState.PLACED_VERIFIED), None)
                slots = tuple(slot for slot in slots if slot.layer == layer)
            return tuple(slot for slot in slots
                         if self.states[slot.slot_id] == SlotState.EMPTY
                         and all(self.states[key] == SlotState.PLACED_VERIFIED for key in slot.supports))

    def reserve(self, slot_id, object_id):
        with self._lock:
            if slot_id not in {s.slot_id for s in self.ready_slots()}:
                raise ValueError("slot unavailable or support unverified")
            if not object_id or object_id in self.allocated_block_ids():
                raise ValueError("block identity missing or already allocated")
            self.reservations[slot_id] = object_id
            self.states[slot_id] = SlotState.RESERVED

    def mark_unverified(self, slot_id):
        with self._lock:
            if slot_id not in self.reservations:
                raise ValueError("unreserved slot")
            self.states[slot_id] = SlotState.UNVERIFIED

    def commit_verified(self, slot_id, object_id):
        with self._lock:
            if self.states[slot_id] != SlotState.UNVERIFIED or self.reservations.get(slot_id) != object_id:
                raise ValueError("verification does not match pending transaction")
            self.occupants[slot_id] = self.reservations.pop(slot_id)
            self.states[slot_id] = SlotState.PLACED_VERIFIED

    def cancel_before_pick(self, slot_id):
        with self._lock:
            if self.states[slot_id] != SlotState.RESERVED:
                raise ValueError("cannot erase uncertain post-pick occupancy")
            self.reservations.pop(slot_id)
            self.states[slot_id] = SlotState.EMPTY
