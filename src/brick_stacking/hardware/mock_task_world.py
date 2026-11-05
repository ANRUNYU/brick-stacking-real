"""Deterministic scene fixture, NOT a physics engine or vision reconstruction."""
from dataclasses import replace
from brick_stacking.models.scene_state import BlockLocation, SceneSnapshot


class MockTaskWorld:
    backend = "mock"
    hardware_enabled = False
    epoch = "mock_task_epoch_1"
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

    def observe(self):
        self.now_s += self.tick_s
        self._counter += 1
        return SceneSnapshot(f"mock_obs_{self._counter}", self.epoch, self.now_s,
            self.clock_domain, tuple(self.blocks.values()), self.hand_clear, "synthetic")

    def step(self, stage, block_id, slot):
        self.events.append({"stage": stage, "block_id": block_id, "slot_id": slot.slot_id,
                            "physical_execution": False})
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
