"""Offline-only fail-closed gate. NOT a real robot safety implementation."""
from dataclasses import dataclass
import math

from brick_stacking.contracts import ArmState, Permit


@dataclass(frozen=True)
class StepEvidence:
    feedback: ArmState
    calibration_valid: bool | None
    trajectory_hash: str
    permit: Permit | None


class OfflineSafetyGate:
    def __init__(self, *, max_age_s):
        if not math.isfinite(max_age_s) or max_age_s <= 0:
            raise ValueError("positive observation age required")
        self.max_age_s = max_age_s

    def check(self, config, port, scene, *, now_s, clock_domain, epoch):
        if config["project"] != {"dry_run": True, "environment": "offline"}:
            raise ValueError("offline dry_run configuration required")
        if getattr(port, "backend", None) != "mock" or getattr(port, "hardware_enabled", None) is not False:
            raise ValueError("real/device adapters are not accepted by offline executor")
        if scene.source != "synthetic" or scene.epoch != epoch or scene.clock_domain != clock_domain:
            raise ValueError("mock source/epoch/clock mismatch")
        age = now_s - scene.stamp_s
        if not math.isfinite(age) or not 0 <= age <= self.max_age_s:
            raise ValueError("stale/future observation")
        operation = config["operation"]
        if operation["mode"] in {"AUTONOMY_TRIAL", "COMPETITION_AUTONOMOUS"} and operation["manual_intervention_allowed"]:
            raise ValueError("autonomous workflow cannot depend on manual recovery")

    def check_step_evidence(self, evidence: StepEvidence | None, *, now_s, clock_domain, epoch,
                            device_id, config_hash, calibration_hash, scene_version):
        """Check the contract evidence for the current mock step."""
        if evidence is None:
            raise ValueError("step evidence is missing")
        if evidence.calibration_valid is not True or not calibration_hash:
            raise ValueError("calibration is invalid or unknown")

        state = evidence.feedback
        if (state["validity"] != "VALID" or state["source"] != "mock"
                or state["device_id"] != device_id or state["clock_domain"] != clock_domain
                or state["epoch"] != epoch):
            raise ValueError("invalid mock feedback identity, source, epoch or clock")
        age = now_s - state["host_receive_stamp"]
        if not math.isfinite(age) or not 0 <= age <= self.max_age_s:
            raise ValueError("stale/future execution feedback")

        permit = evidence.permit
        if permit is None:
            raise ValueError("execution permit is unknown")
        expected = {
            "device_id": device_id,
            "trajectory_hash": evidence.trajectory_hash,
            "config_hash": config_hash,
            "calibration_hash": calibration_hash,
            "scene_version": scene_version,
        }
        if not evidence.trajectory_hash or any(permit.get(key) != value for key, value in expected.items()):
            raise ValueError("execution permit does not match current step context")
        remaining = permit["valid_until_host_monotonic_s"] - now_s
        if not math.isfinite(remaining) or remaining <= 0:
            raise ValueError("execution permit has expired or has invalid expiry")
        if remaining > self.max_age_s:
            raise ValueError("execution permit exceeds the offline freshness window")
