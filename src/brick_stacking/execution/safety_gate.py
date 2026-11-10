"""Offline-only fail-closed gate. NOT a real robot safety implementation.

Live contracts.Permit authority remains D/M SafetyGate at execution time.
This module also exposes a dry-run / arm-disabled *issuance diagnostic* that
assembles Permit fields under MockArm (hardware_enabled=False) with
executable=false. The diagnostic never raises control_ready and never claims
live formal-grasp authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from brick_stacking.contracts import ArmState, Permit

DRY_RUN_ISSUANCE_SCHEMA = "safety-gate-dry-run-issuance-0.1"
LIVE_PERMIT_REQUIRED_FIELDS = (
    "device_id",
    "trajectory_hash",
    "config_hash",
    "calibration_hash",
    "scene_version",
    "valid_until_host_monotonic_s",
)
# Explicitly labeled probe-only hash; never a formal PlanBundle trajectory.
PROBE_TRAJECTORY_HASH = "dry-run-probe:safety-gate-plumbing-only"


@dataclass(frozen=True)
class StepEvidence:
    feedback: ArmState
    calibration_valid: bool | None
    trajectory_hash: str
    permit: Permit | None


def _require_mock_arm_disabled(arm: Any) -> None:
    if getattr(arm, "backend", None) != "mock":
        raise ValueError("dry-run issuance requires MockArm backend")
    if getattr(arm, "hardware_enabled", None) is not False:
        raise ValueError("dry-run issuance requires hardware_enabled=False")
    if not callable(getattr(arm, "read_state", None)):
        raise ValueError("dry-run issuance requires arm.read_state()")


def _field(status: str, *, detail: str, value: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": status, "detail": detail}
    if value is not None:
        payload["value"] = value
    return payload


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

    def issue_dry_run_diagnostic(
        self,
        *,
        arm: Any,
        config_hash: str | None = None,
        calibration_hash: str | None = None,
        scene_version: str | None = None,
        trajectory_hash: str | None = None,
        now_s: float | None = None,
        validity_window_s: float | None = None,
        verify_gate_accepts: bool = True,
        run_plumbing_self_check: bool = True,
    ) -> dict[str, Any]:
        """Dry-run / arm-disabled SafetyGate issuance diagnostic.

        Assembles contracts.Permit *fields* under MockArm (hardware_enabled=False).
        Always returns executable=false and live_permit=null. Does not raise
        control_ready. A complete field set may produce a dry-run draft that
        OfflineSafetyGate.check_step_evidence accepts — still not live formal
        authority.

        If trajectory_hash is omitted, lists it as still missing (do not invent
        a PlanBundle hash). Optional plumbing self-check uses a labeled probe
        hash only to prove issuance→check wiring.
        """
        _require_mock_arm_disabled(arm)
        feedback = arm.read_state()
        device_id = feedback.get("device_id")
        stamp = feedback.get("host_receive_stamp")
        epoch = feedback.get("epoch")
        clock_domain = feedback.get("clock_domain")
        if now_s is None:
            now_s = float(stamp)
        window = self.max_age_s if validity_window_s is None else float(validity_window_s)
        if not math.isfinite(window) or window <= 0 or window > self.max_age_s:
            raise ValueError("validity window must be positive and within offline freshness")

        field_status: dict[str, dict[str, Any]] = {
            "device_id": (
                _field(
                    "PRESENT_FROM_MOCK_ARM",
                    detail="MockArm ArmState.device_id (hardware_enabled=False); not live arm",
                    value=device_id,
                )
                if device_id
                else _field("MISSING", detail="MockArm returned empty device_id")
            ),
            "trajectory_hash": (
                _field(
                    "PRESENT_FROM_PLAN_BUNDLE",
                    detail="trajectory_hash supplied to dry-run issuer (not invented)",
                    value=trajectory_hash,
                )
                if trajectory_hash
                else _field(
                    "MISSING_PLAN_BUNDLE",
                    detail="no PlanBundle/trajectory_hash; dry-run issuer refuses to invent",
                )
            ),
            "config_hash": (
                _field(
                    "PRESENT",
                    detail="config_hash supplied to dry-run issuer",
                    value=config_hash,
                )
                if config_hash
                else _field("MISSING", detail="config_hash not supplied")
            ),
            "calibration_hash": (
                _field(
                    "PRESENT",
                    detail="calibration_hash supplied to dry-run issuer",
                    value=calibration_hash,
                )
                if calibration_hash
                else _field("MISSING", detail="calibration_hash not supplied")
            ),
            "scene_version": (
                _field(
                    "PRESENT",
                    detail="scene_version supplied to dry-run issuer",
                    value=scene_version,
                )
                if scene_version
                else _field("MISSING", detail="scene_version not supplied")
            ),
            "valid_until_host_monotonic_s": _field(
                "PRESENT_FROM_ISSUANCE_CLOCK",
                detail=(
                    "dry-run issuer sets valid_until = now + min(window, max_age_s); "
                    "live path still requires live SafetyGate issuance clock"
                ),
                value=float(now_s) + window,
            ),
        }

        missing_fields = [
            name
            for name, info in field_status.items()
            if not str(info.get("status", "")).startswith("PRESENT")
        ]
        fields_complete = not missing_fields

        draft_permit: Permit | None = None
        gate_accepts_draft: bool | None = None
        gate_accept_error: str | None = None
        if fields_complete:
            draft_permit = {
                "device_id": str(device_id),
                "trajectory_hash": str(trajectory_hash),
                "config_hash": str(config_hash),
                "calibration_hash": str(calibration_hash),
                "scene_version": str(scene_version),
                "valid_until_host_monotonic_s": float(now_s) + window,
            }
            if verify_gate_accepts:
                try:
                    self.check_step_evidence(
                        StepEvidence(
                            feedback=feedback,
                            calibration_valid=True,
                            trajectory_hash=str(trajectory_hash),
                            permit=draft_permit,
                        ),
                        now_s=float(now_s),
                        clock_domain=str(clock_domain),
                        epoch=str(epoch),
                        device_id=str(device_id),
                        config_hash=str(config_hash),
                        calibration_hash=str(calibration_hash),
                        scene_version=str(scene_version),
                    )
                    gate_accepts_draft = True
                except ValueError as exc:
                    gate_accepts_draft = False
                    gate_accept_error = str(exc)

        plumbing: dict[str, Any] | None = None
        if run_plumbing_self_check:
            plumbing = self._plumbing_self_check(
                arm=arm,
                feedback=feedback,
                now_s=float(now_s),
                window=window,
                config_hash=config_hash or "dry-run-probe-config",
                calibration_hash=calibration_hash or "dry-run-probe-calibration",
                scene_version=scene_version or "dry-run-probe-scene",
            )

        still_missing_for_formal = list(missing_fields)
        for hold in (
            "live SafetyGate issuance authority (formal contracts.Permit)",
            "fresh VALID live ArmState.device_id (recorded/mock do not count as live)",
            "host/safety policy raise of control_ready",
            "actuator / arm power enable before real motion",
        ):
            if hold not in still_missing_for_formal:
                still_missing_for_formal.append(hold)

        only_hw_policy = fields_complete and gate_accepts_draft is True

        return {
            "schema_version": DRY_RUN_ISSUANCE_SCHEMA,
            "kind": "dry_run_arm_disabled",
            "executable": False,
            "live_permit": None,
            "control_ready": False,
            "motion_enabled": False,
            "formal_grasp_entry_allowed": False,
            "issuance_attempted": True,
            "issuance_fields_complete": fields_complete,
            "only_hardware_enable_and_policy_remaining": only_hw_policy,
            "authority": {
                "live_issuer": "D/M SafetyGate at execution (contracts.Permit)",
                "dry_run_diagnostic_issuer": "OfflineSafetyGate.issue_dry_run_diagnostic",
                "shadow_eligibility_issuer": "pre_grasp_gates (m-diagnostic-permit-eligibility-0.1)",
                "not_authority_for": [
                    "formal_grasp_entry",
                    "control_ready",
                    "CAN / actuator enable",
                    "arm.execute_trajectory on live hardware",
                ],
                "required_live_fields": list(LIVE_PERMIT_REQUIRED_FIELDS),
            },
            "mock_arm": {
                "backend": getattr(arm, "backend", None),
                "hardware_enabled": getattr(arm, "hardware_enabled", None),
                "device_id": device_id,
                "clock_domain": clock_domain,
                "epoch": epoch,
            },
            "field_status": field_status,
            "still_missing_fields": missing_fields,
            "still_missing_for_formal": still_missing_for_formal,
            "draft_permit": draft_permit,
            "gate_accepts_draft": gate_accepts_draft,
            "gate_accept_error": gate_accept_error,
            "plumbing_self_check": plumbing,
            "notes": [
                "Dry-run draft is executable=false and must not be copied into live StepEvidence for formal grasp.",
                "MockArm device_id / issuance clock are dry-run only; live VALID arm feedback still required for formal.",
                "PlanBundle trajectory_hash must come from planning; this issuer never invents it.",
            ],
        }

    def _plumbing_self_check(
        self,
        *,
        arm: Any,
        feedback: ArmState,
        now_s: float,
        window: float,
        config_hash: str,
        calibration_hash: str,
        scene_version: str,
    ) -> dict[str, Any]:
        """Prove issuance→check wiring with an explicitly labeled probe hash."""
        _require_mock_arm_disabled(arm)
        probe_permit: Permit = {
            "device_id": str(feedback["device_id"]),
            "trajectory_hash": PROBE_TRAJECTORY_HASH,
            "config_hash": config_hash,
            "calibration_hash": calibration_hash,
            "scene_version": scene_version,
            "valid_until_host_monotonic_s": now_s + window,
        }
        accepted = False
        error: str | None = None
        try:
            self.check_step_evidence(
                StepEvidence(
                    feedback=feedback,
                    calibration_valid=True,
                    trajectory_hash=PROBE_TRAJECTORY_HASH,
                    permit=probe_permit,
                ),
                now_s=now_s,
                clock_domain=str(feedback["clock_domain"]),
                epoch=str(feedback["epoch"]),
                device_id=str(feedback["device_id"]),
                config_hash=config_hash,
                calibration_hash=calibration_hash,
                scene_version=scene_version,
            )
            accepted = True
        except ValueError as exc:
            error = str(exc)
        return {
            "used_probe_trajectory_hash": True,
            "probe_trajectory_hash": PROBE_TRAJECTORY_HASH,
            "gate_accepts_complete_dry_run_permit": accepted,
            "error": error,
            "note": (
                "Proves OfflineSafetyGate issuance→check path under MockArm; "
                "probe hash is not a formal PlanBundle trajectory_hash"
            ),
        }
