"""Independent offline single-arm transaction loop with bounded retry."""
import math
from brick_stacking.models.scene_state import BlockLocation
from brick_stacking.models.task_state import TaskStage, TaskResult
from brick_stacking.planning.task_scheduler import choose_task
from brick_stacking.execution.safety_gate import OfflineSafetyGate
from brick_stacking.verification.placement_verification import verify_placement, verify_stability


class OfflineExecutionManager:
    def __init__(self, *, config, scene_manager, port, event_sink):
        self.config, self.scene_manager, self.port, self.event_sink = config, scene_manager, port, event_sink
        task = config["task"]
        for name in ("max_observation_age_s", "xy_tolerance_m", "z_tolerance_m", "stable_spread_m", "stability_span_s"):
            if not math.isfinite(task[name]) or task[name] <= 0:
                raise ValueError(f"positive finite task parameter required: {name}")
        if type(task["max_grasp_retries"]) is not int or not 0 <= task["max_grasp_retries"] <= 5:
            raise ValueError("bounded integer retry policy required")
        if type(task["stability_samples"]) is not int or not 2 <= task["stability_samples"] <= 1000:
            raise ValueError("bounded stability window required")
        self.gate = OfflineSafetyGate(max_age_s=task["max_observation_age_s"])
        self.stage = TaskStage.INIT
        self.recovery_attempts = 0
        self.last_stamp_s = -1.

    def _stage(self, stage, **details):
        self.stage = stage
        self.event_sink("stage", {"stage": stage.value, **details})

    def _observe(self):
        scene = self.port.observe()
        self.gate.check(self.config, self.port, scene, now_s=self.port.now_s,
                        clock_domain=self.port.clock_domain, epoch=self.port.epoch)
        if scene.stamp_s <= self.last_stamp_s:
            raise ValueError("new observation required; duplicate/reset clock")
        self.last_stamp_s = scene.stamp_s
        self.latest_snapshot = scene
        self.event_sink("observation", {"id": scene.observation_id, "stamp_s": scene.stamp_s,
                                      "source": scene.source, "hand_clear": scene.hand_clear})
        return scene

    def _step(self, stage, block_id, slot):
        self.gate.check(self.config, self.port, self.latest_snapshot, now_s=self.port.now_s,
                        clock_domain=self.port.clock_domain, epoch=self.port.epoch)
        result = self.port.step(stage, block_id, slot)
        if result is not True and stage != "GRASP":
            raise ValueError(f"mock action failed: {stage}")
        return result

    def _result(self, reason):
        return TaskResult(self.stage, tuple(self.scene_manager.occupants), reason, self.recovery_attempts)

    def _verify_transition(self, phase, block_id, slot, before, after):
        """Optional additional evidence supplied by the single-block workflow."""

    def _halt(self, reason):
        self._stage(TaskStage.SAFE_HALT, reason=reason)
        # Reject device adapters before invoking even a stop method.
        if getattr(self.port, "backend", None) == "mock" and getattr(self.port, "hardware_enabled", None) is False:
            try:
                self.port.stop()
            except Exception as exc:
                reason += f"; mock_stop_error={exc}"
        return self._result(reason)

    def run(self):
        retries = {}
        v = self.config["task"]
        try:
            if getattr(self.port, "backend", None) != "mock" or getattr(self.port, "hardware_enabled", None) is not False:
                return self._halt("offline executor refuses hardware adapters")
            while len(self.scene_manager.occupants) < len(self.scene_manager.slots):
                self._stage(TaskStage.OBSERVE)
                snapshot = self._observe()
                self._stage(TaskStage.PLAN)
                selected = choose_task(snapshot, self.scene_manager)
                if selected is None:
                    return self._halt("no safely selectable supply block / support slot")
                block, slot = selected
                self.scene_manager.reserve(slot.slot_id, block.object_id)
                self._stage(TaskStage.PRE_GRASP, object_id=block.object_id, slot_id=slot.slot_id)
                self._step("PRE_GRASP", block.object_id, slot)
                self._stage(TaskStage.GRASP)
                ok = self._step("GRASP", block.object_id, slot)
                self._stage(TaskStage.VERIFY_PICK)
                picked = self._observe()
                held = next((b for b in picked.blocks if b.object_id == block.object_id), None)
                if not ok:
                    # Retry only when a new observation confirms the block is
                    # still in supply and the mock hand is clear/empty.
                    if (self.port.payload is not None or not picked.hand_clear or held is None
                            or not held.visible or held.ambiguous or held.location != BlockLocation.SUPPLY):
                        return self._halt("failed grasp has uncertain payload")
                    used = retries.get(block.object_id, 0)
                    if used >= v["max_grasp_retries"]:
                        return self._halt("grasp retry limit exhausted")
                    retries[block.object_id] = used + 1
                    self.recovery_attempts += 1
                    self.scene_manager.cancel_before_pick(slot.slot_id)
                    self._stage(TaskStage.REOBSERVE)
                    continue
                if (self.port.payload != block.object_id or held is None or not held.visible or held.ambiguous
                        or held.location != BlockLocation.HELD_LEFT):
                    return self._halt("pick not verified")
                self._verify_transition("PICK", block.object_id, slot, snapshot, picked)
                self._stage(TaskStage.TRANSPORT)
                self._step("TRANSPORT", block.object_id, slot)
                self._stage(TaskStage.PLACE)
                self._step("PLACE", block.object_id, slot)
                self.scene_manager.mark_unverified(slot.slot_id)
                self._stage(TaskStage.RETREAT)
                self._step("RETREAT", block.object_id, slot)
                self._stage(TaskStage.VERIFY_PLACE)
                after = self._observe()
                verdict = verify_placement(after, block.object_id, slot,
                    xy_tolerance_m=v["xy_tolerance_m"], z_tolerance_m=v["z_tolerance_m"])
                if verdict != "PASS":
                    return self._halt(f"placement {verdict}; occupancy retained as unverified")
                self._verify_transition("PLACE", block.object_id, slot, picked, after)
                self.scene_manager.commit_verified(slot.slot_id, block.object_id)
            self._stage(TaskStage.FINAL_STABILITY_CHECK)
            window = [self._observe() for _ in range(v["stability_samples"])]
            if not verify_stability(window, self.scene_manager.occupants, self.scene_manager.slots,
                    minimum_span_s=v["stability_span_s"], spread_m=v["stable_spread_m"],
                    xy_tolerance_m=v["xy_tolerance_m"], z_tolerance_m=v["z_tolerance_m"]):
                return self._halt("structure stability unverified")
            self._stage(TaskStage.DONE)
            return self._result("offline position/state workflow completed; no physics or hardware acceptance")
        except Exception as exc:
            return self._halt(f"{type(exc).__name__}: {exc}")
