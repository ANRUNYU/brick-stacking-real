"""A one-slot mock pick/place workflow using the existing transaction loop."""

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from threading import Lock
from time import monotonic

from brick_stacking.execution.execution_manager import OfflineExecutionManager
from brick_stacking.execution.safety_gate import StepEvidence


@dataclass(frozen=True)
class StepRequest:
    stage: str
    block_id: str
    slot_id: str
    scene_version: str
    config_hash: str


class PickPlaceFSM(OfflineExecutionManager):
    """One offline transaction with per-step evidence and a run deadline."""

    def __init__(self, *, config, scene_manager, port, event_sink,
                 evidence_for: Callable[[StepRequest], StepEvidence | None],
                 device_id: str, calibration_hash: str, timeout_s: float,
                 clock: Callable[[], float] = monotonic):
        if len(scene_manager.slots) != 1 or scene_manager.occupants or scene_manager.reservations:
            raise ValueError("single-block FSM requires one fresh slot")
        if not device_id:
            raise ValueError("explicit mock device identity required")
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("positive finite task timeout required")
        config = deepcopy(config)
        super().__init__(config=config, scene_manager=scene_manager, port=port, event_sink=event_sink)
        self.config_hash = sha256(json.dumps(config, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self._evidence_for = evidence_for
        self._device_id = device_id
        self._calibration_hash = calibration_hash
        self._timeout_s = timeout_s
        self._clock = clock
        self._run_lock = Lock()
        self._deadline = None

    def run(self):
        with self._run_lock:
            if self._deadline is not None:
                raise RuntimeError("single-block FSM is single use")
            self._deadline = self._clock() + self._timeout_s
        return super().run()

    def _check_deadline(self):
        if not self._clock() < self._deadline:
            raise TimeoutError("single-block task deadline exceeded")

    def _observe(self):
        self._check_deadline()
        scene = super()._observe()
        self._check_deadline()
        return scene

    def _step(self, stage, block_id, slot):
        self._check_deadline()
        request = StepRequest(stage, block_id, slot.slot_id,
                              self.latest_snapshot.observation_id, self.config_hash)
        evidence = self._evidence_for(request)
        self._check_deadline()
        self.gate.check_step_evidence(
            evidence, now_s=self.port.now_s, clock_domain=self.port.clock_domain,
            epoch=self.port.epoch, device_id=self._device_id, config_hash=self.config_hash,
            calibration_hash=self._calibration_hash, scene_version=request.scene_version,
        )
        result = super()._step(stage, block_id, slot)
        self.event_sink("step_dispatched", {
            "stage": stage, "block_id": block_id, "slot_id": slot.slot_id,
            "scene_version": request.scene_version, "config_hash": request.config_hash,
            "sample_id": evidence.feedback["sample_id"],
            "trajectory_hash": evidence.trajectory_hash,
            "calibration_hash": self._calibration_hash,
        })
        return result
