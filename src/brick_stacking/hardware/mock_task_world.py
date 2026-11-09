"""Deterministic scene fixture, NOT a physics engine or vision reconstruction."""
from contextlib import contextmanager
from dataclasses import dataclass, replace
from threading import Lock
from uuid import uuid4

from brick_stacking.models.scene_state import BlockLocation, SceneSnapshot


@dataclass(frozen=True)
class MockCommand:
    epoch: str
    sequence: int
    stage: str
    block_id: str
    slot_id: str


class MockTaskWorld:
    backend = "mock"
    hardware_enabled = False
    clock_domain = "synthetic_task_clock"

    def __init__(self, blocks, *, tick_s, fail_first_grasps=0, placement_error_m=0.):
        if tick_s <= 0 or fail_first_grasps < 0:
            raise ValueError("invalid mock scenario")
        self.blocks = {b.object_id: b for b in blocks}
        self.now_s = 0.
        self.tick_s = tick_s
        self.fail_first_grasps = fail_first_grasps
        self.placement_error_m = placement_error_m
        self.payload = None
        self.hand_clear = True
        self.events = []
        self._counter = 0
        self.epoch = uuid4().hex
        self._lock = Lock()
        self._active = False
        self._sequence = 0

    @contextmanager
    def session(self):
        """Rotate command identity while preserving the simulated physical scene."""
        with self._lock:
            if self._active:
                raise RuntimeError("mock world already has an active run")
            self.epoch = uuid4().hex
            self._sequence = 0
            self._active = True
        try:
            yield self.epoch
        finally:
            with self._lock:
                self._active = False

    def observe(self):
        self.now_s += self.tick_s
        self._counter += 1
        return SceneSnapshot(f"mock_obs_{self._counter}", self.epoch, self.now_s,
            self.clock_domain, tuple(self.blocks.values()), self.hand_clear, "synthetic")

    def dispatch(self, command: MockCommand, slot):
        with self._lock:
            if not self._active or command.epoch != self.epoch:
                raise ValueError("mock command belongs to an inactive or old run")
            if command.sequence != self._sequence + 1 or command.slot_id != slot.slot_id:
                raise ValueError("mock command is repeated, out of sequence or for a different slot")
            if command.stage not in {"PRE_GRASP", "GRASP", "TRANSPORT", "PLACE", "RETREAT"}:
                raise ValueError("unsupported mock action")
            self._sequence = command.sequence
            self.events.append({
                "stage": command.stage, "block_id": command.block_id, "slot_id": command.slot_id,
                "epoch": command.epoch, "sequence": command.sequence, "physical_execution": False,
            })
            return self._apply(command.stage, command.block_id, slot)

    def _apply(self, stage, block_id, slot):
        block = self.blocks[block_id]
        if stage == "GRASP":
            if self.fail_first_grasps:
                self.fail_first_grasps -= 1
                return False
            self.payload = block_id
            self.hand_clear = False
            self.blocks[block_id] = replace(block, location=BlockLocation.HELD_LEFT,
                                           center_m=(block.center_m[0], block.center_m[1], block.center_m[2] + .1))
        elif stage == "PLACE":
            if self.payload != block_id:
                raise ValueError("mock placement requires owned payload")
            center = (slot.center_m[0] + self.placement_error_m, *slot.center_m[1:])
            self.blocks[block_id] = replace(block, center_m=center, location=BlockLocation.PLACED)
            self.payload = None
        elif stage == "RETREAT":
            self.hand_clear = True
        return True

    def stop(self):
        # No automatic release, reset, re-home or invented payload recovery.
        self.events.append({"stage": "MOCK_STOP", "physical_execution": False})
