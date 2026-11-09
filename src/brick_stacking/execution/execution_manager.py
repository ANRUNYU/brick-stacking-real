"""Independent offline single-arm transaction loop with bounded retry."""
import math
from threading import Lock

from brick_stacking.hardware.mock_task_world import MockCommand
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
        self.max_reobservations = task.get("max_reobservations", 2)
        if type(self.max_reobservations) is not int or not 0 <= self.max_reobservations <= 5:
            raise ValueError("bounded integer reobservation policy required")
        if type(task["stability_samples"]) is not int or not 2 <= task["stability_samples"] <= 1000:
            raise ValueError("bounded stability window required")
        self.gate = OfflineSafetyGate(max_age_s=task["max_observation_age_s"])
        self.stage = TaskStage.INIT
        self.recovery_attempts = 0
        self.reobservations = 0
        self.last_stamp_s = -1.
        self._observation_ids = set()
        self._sequence = 0
        self._started = False
        self._run_lock = Lock()

    def _stage(self, stage, **details):
        self.stage = stage
        self.event_sink("stage", {"stage": stage.value, **details})

    def _observe(self):
        scene = self.port.observe()
        self.gate.check(self.config, self.port, scene, now_s=self.port.now_s,
                        clock_domain=self._clock_domain, epoch=self._epoch)
        if scene.stamp_s <= self.last_stamp_s or scene.observation_id in self._observation_ids:
            raise ValueError("new observation required; duplicate/reset clock or observation ID")
        self.last_stamp_s = scene.stamp_s
        self._observation_ids.add(scene.observation_id)
        self.latest_snapshot = scene
        self.event_sink("observation", {"id": scene.observation_id, "stamp_s": scene.stamp_s,
                                      "source": scene.source, "hand_clear": scene.hand_clear,
                                      "epoch": scene.epoch})
        return scene

    def _step(self, stage, block_id, slot):
        self.gate.check(self.config, self.port, self.latest_snapshot, now_s=self.port.now_s,
                        clock_domain=self._clock_domain, epoch=self._epoch)
        self._sequence += 1
        command = MockCommand(self._epoch, self._sequence, stage, block_id, slot.slot_id)
        result = self.port.dispatch(command, slot)
        self.event_sink("mock_command", {
            "epoch": command.epoch, "sequence": command.sequence, "stage": stage,
            "block_id": block_id, "slot_id": slot.slot_id,
        })
        if result is not True and stage != "GRASP":
            raise ValueError(f"mock action failed: {stage}")
        return result

    def _result(self, reason):
        return TaskResult(self.stage, tuple(self.scene_manager.occupants), reason, self.recovery_attempts,
                          reobservations=self.reobservations)

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

    def _placement_verdict(self, snapshot, block_id, slot, *, require_hand_clear=True):
        task = self.config["task"]
        return verify_placement(snapshot, block_id, slot, xy_tolerance_m=task["xy_tolerance_m"],
                                z_tolerance_m=task["z_tolerance_m"], require_hand_clear=require_hand_clear)

    def _reobserve(self, reason):
        self.reobservations += 1
        self._stage(TaskStage.REOBSERVE, reason=reason, count=self.reobservations)
        return self._observe()

    def _check_structure(self, snapshot):
        for attempt in range(self.max_reobservations + 1):
            verdicts = {
                key: self._placement_verdict(snapshot, block_id, self.scene_manager.slots[key],
                                             require_hand_clear=False)
                for key, block_id in self.scene_manager.occupants.items()
            }
            failed = [key for key, verdict in verdicts.items() if verdict == "FAIL"]
            unknown = [key for key, verdict in verdicts.items() if verdict == "UNOBSERVABLE"]
            if not failed and not unknown:
                return snapshot
            if failed or attempt == self.max_reobservations:
                affected = self.scene_manager.invalidate_supports(failed + unknown)
                reason = "placed structure changed or collapsed" if failed else "structure reobservation limit exhausted"
                self.event_sink("structure_invalidated", {
                    "reason": reason, "slots": affected, "observation_id": snapshot.observation_id,
                })
                raise ValueError(reason)
            snapshot = self._reobserve("committed placement temporarily unobservable")

    def _rescan(self, snapshot):
        if self.port.payload is not None or not snapshot.hand_clear or any(
            block.location not in {BlockLocation.SUPPLY, BlockLocation.PLACED} for block in snapshot.blocks
        ):
            raise ValueError("rescan requires clear hand and known block locations")
        allocations = {}
        for block in snapshot.blocks:
            if block.location != BlockLocation.PLACED:
                continue
            matching = [key for key, slot in self.scene_manager.slots.items()
                        if self._placement_verdict(snapshot, block.object_id, slot) == "PASS"]
            if len(matching) != 1 or matching[0] in allocations:
                raise ValueError("rescan found ambiguous or out-of-slot placement")
            allocations[matching[0]] = block.object_id
        self.scene_manager.restore_verified(allocations)
        self.event_sink("rescan", {
            "epoch": self._epoch, "observation_id": snapshot.observation_id, "verified": allocations,
        })

    def run(self):
        with self._run_lock:
            if self._started:
                raise RuntimeError("create a new execution manager and scene manager for restart")
            self._started = True
        if getattr(self.port, "backend", None) != "mock" or getattr(self.port, "hardware_enabled", None) is not False:
            return self._halt("offline executor refuses hardware adapters")
        try:
            with self.port.session() as self._epoch:
                self._clock_domain = self.port.clock_domain
                return self._run_session()
        except Exception as exc:
            # A failed session acquisition must not stop another active run.
            self._stage(TaskStage.SAFE_HALT, reason=str(exc))
            return self._result(str(exc))

    def _run_session(self):
        retries = {}
        v = self.config["task"]
        try:
            self._stage(TaskStage.OBSERVE)
            snapshot = self._observe()
            self._rescan(snapshot)
            while len(self.scene_manager.occupants) < len(self.scene_manager.slots):
                if snapshot is None:
                    self._stage(TaskStage.OBSERVE)
                    snapshot = self._check_structure(self._observe())
                self._stage(TaskStage.PLAN)
                selected = choose_task(snapshot, self.scene_manager)
                for _ in range(self.max_reobservations):
                    if selected is not None:
                        break
                    snapshot = self._check_structure(self._reobserve("no selectable task"))
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
                picked = self._check_structure(self._observe())
                held = next((b for b in picked.blocks if b.object_id == block.object_id), None)
                for _ in range(self.max_reobservations):
                    if held is not None and held.visible and not held.ambiguous:
                        break
                    picked = self._check_structure(self._reobserve("pick temporarily unobservable"))
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
                    snapshot = None
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
                after = self._check_structure(self._observe())
                verdict = self._placement_verdict(after, block.object_id, slot)
                for _ in range(self.max_reobservations):
                    if verdict != "UNOBSERVABLE":
                        break
                    after = self._check_structure(self._reobserve("placement temporarily unobservable"))
                    verdict = self._placement_verdict(after, block.object_id, slot)
                if verdict != "PASS":
                    return self._halt(f"placement {verdict}; occupancy retained as unverified")
                self._verify_transition("PLACE", block.object_id, slot, picked, after)
                self.scene_manager.commit_verified(slot.slot_id, block.object_id)
                snapshot = None
            self._stage(TaskStage.FINAL_STABILITY_CHECK)
            window = [self._check_structure(self._observe()) for _ in range(v["stability_samples"])]
            if not verify_stability(window, self.scene_manager.occupants, self.scene_manager.slots,
                    minimum_span_s=v["stability_span_s"], spread_m=v["stable_spread_m"],
                    xy_tolerance_m=v["xy_tolerance_m"], z_tolerance_m=v["z_tolerance_m"]):
                affected = self.scene_manager.invalidate_supports(self.scene_manager.occupants)
                self.event_sink("structure_invalidated", {"reason": "stability unverified", "slots": affected})
                return self._halt("structure stability unverified")
            self._stage(TaskStage.DONE)
            return self._result("offline position/state workflow completed; no physics or hardware acceptance")
        except Exception as exc:
            return self._halt(f"{type(exc).__name__}: {exc}")
