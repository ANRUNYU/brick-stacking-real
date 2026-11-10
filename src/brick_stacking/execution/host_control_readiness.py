"""Host/safety control_ready + motion_enabled checklist.

Gate ladder (machine-auditable):
  vision_pre_grasp_ready
    → dry_run_grasp_entry_ready   (MockArm / arm-disabled full chain)
    → formal_grasp_entry_allowed  (live Permit + live VALID arm)
    → control_ready               (attest-gated; THIS REPORTER NEVER RAISES)

Hard safety (large-motion): this module always reports control_ready=false and
motion_enabled=false. dry_run_grasp_entry_ready may be true. Operator policy
attest switch exists (default closed) and is never auto-opened; even when
attested, elevation is deferred — do not unlock real large arm motion here.
Never invents live contracts.Permit, never opens CAN.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from brick_stacking.arm.adapter import MockArm
from brick_stacking.arm.arm_state_validity import (
    classify_arm_state,
    unwrap_arm_state,
)
from brick_stacking.arm.rest_state_capture import (
    is_rest_state_capture_draft,
    is_rest_state_capture_enabled,
    rest_state_capture_gate_report,
)
from brick_stacking.arm.v2_wrist_readonly import HARD_BLOCK_ID as J6J7_HARD_BLOCK_ID
from brick_stacking.execution.host_policy_attest import (
    SCHEMA as ATTEST_SCHEMA,
    HostPolicyAttest,
    empty_attest,
    load_host_policy_attest,
)
from brick_stacking.execution.safety_gate import (
    FORMAL_PERMIT_BLOCKED_BY_LIVE_ARM,
    LIVE_PERMIT_REQUIRED_FIELDS,
    OfflineSafetyGate,
    StepEvidence,
)
from brick_stacking.runtime.config_loader import load_config

SCHEMA = "host-control-readiness-0.2"
DRY_RUN_PROBE_SCHEMA = "host-dry-run-arm-disabled-0.1"

# Machine-readable formal-entry root blockers (no-motion software ceiling).
FORMAL_BLOCK_J6J7_READONLY = "j6_j7_readonly"
FORMAL_BLOCK_AWAITING_LIVE_ARM = "awaiting_live_arm"

GATE_DEFINITIONS = {
    "vision_pre_grasp_ready": (
        "Vision-side pre_grasp evidence gates clear "
        "(pre_grasp_gates.evidence_gates_clear). Not formal entry."
    ),
    "dry_run_grasp_entry_ready": (
        "vision ready + diagnostic permit_eligible + PlanBundle trajectory_hash "
        "+ ArmState.device_id (recorded/mock OK) + OfflineSafetyGate dry-run "
        "issuance fields complete and gate accepts draft under MockArm."
    ),
    "formal_grasp_entry_allowed": (
        "dry_run_grasp_entry_ready + live contracts.Permit validated by "
        "OfflineSafetyGate against counts_as_live_valid ArmState "
        "(source=real + validity=VALID + seven finite q_rad). "
        "Recorded/mock/fixture arm and dry-run drafts do not count."
    ),
    "control_ready": (
        "Prerequisites: formal_grasp_entry_allowed + explicit "
        "operator_policy_attest (attested=true, default closed). "
        "THIS REPORTER ALWAYS reports control_ready=false (large-motion "
        "safety); elevation deferred to a dedicated host path."
    ),
}


def _context_hashes_from_diagnostic(diagnostic_permit: dict[str, Any] | None) -> dict[str, str | None]:
    """Pull shadow context hashes for dry-run issuance; never invent trajectory_hash."""
    diag = diagnostic_permit or {}
    ctx = diag.get("context_present") or {}
    field = diag.get("live_permit_field_status") or {}

    def _present_value(name: str, *fallback_keys: str) -> str | None:
        info = field.get(name) or {}
        if str(info.get("status", "")).startswith("PRESENT") and info.get("value"):
            return str(info["value"])
        for key in fallback_keys:
            value = ctx.get(key)
            if value:
                return str(value)
        return None

    return {
        "config_hash": _present_value("config_hash", "config_hash_or_profile_hash"),
        "calibration_hash": _present_value("calibration_hash", "calibration_hash"),
        "scene_version": _present_value("scene_version", "scene_version"),
        "trajectory_hash": None,
    }


# Conditions that must hold before host/safety may *consider* raising
# control_ready. Attest is an additional explicit switch.
CONTROL_READY_ELEVATION_CONDITIONS = (
    "vision_pre_grasp_ready_or_evidence_gates_clear",
    "live_contracts_Permit_from_SafetyGate",
    "PlanBundle_trajectory_hash",
    "fresh_live_VALID_ArmState_device_id_matching_permit",
    "offline_dry_run_config_or_explicit_live_host_policy",
    "operator_policy_attest_control_ready",
    "host_policy_decision_to_raise_control_ready",
)

MOTION_ENABLED_ELEVATION_CONDITIONS = (
    "process_started_with_enable_motion",  # host_monitor --enable-motion
    "control_session_confirm_READY",
    "joint_confirm_ENABLE",
    "live_permit_and_control_ready_for_trajectory_path",
)

FORMAL_GRASP_ENTRY_CONDITIONS = (
    "dry_run_grasp_entry_ready",
    "live_contracts_Permit_validated_by_OfflineSafetyGate",
    "live_VALID_ArmState_source_real",
    "permit_device_id_matches_live_arm",
)

DRY_RUN_GRASP_ENTRY_CONDITIONS = (
    "vision_pre_grasp_ready",
    "permit_eligible_diagnostic",
    "PlanBundle_trajectory_hash",
    "ArmState_device_id_recorded_or_live",
    "OfflineSafetyGate_dry_run_issuance_fields_complete",
    "OfflineSafetyGate_gate_accepts_dry_run_draft",
)


@dataclass(frozen=True)
class ChecklistItem:
    id: str
    status: str  # PASS | FAIL | MISSING | POLICY_HOLD | UNKNOWN | PROBED
    blocking: bool
    category: str  # software | live_permit | host_policy | actuator_operator | dry_run
    detail: str
    owner: str


@dataclass(frozen=True)
class HostControlReadiness:
    schema_version: str
    control_ready: bool
    motion_enabled: bool
    formal_grasp_entry_allowed: bool
    formal_grasp_ready: bool
    dry_run_grasp_entry_ready: bool
    vision_pre_grasp_ready: bool | None
    only_operator_enable_remaining: bool
    needs_operator_physical_enable_now: bool
    needs_operator_physical_enable_before_real_motion: bool
    permit_eligible: bool | None
    live_permit: Any
    operator_policy_attest: dict[str, Any]
    gate_ladder: dict[str, Any]
    checklist: tuple[ChecklistItem, ...]
    missing_software: tuple[str, ...]
    missing_field_or_operator: tuple[str, ...]
    hard_blockers: tuple[dict[str, Any], ...]
    formal_grasp_blocked_by: tuple[str, ...]
    live_permit_path: dict[str, Any]
    dry_run_arm_disabled: dict[str, Any] | None
    arm_feedback: dict[str, Any] | None
    elevation_conditions: dict[str, Any]
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["checklist"] = [asdict(item) for item in self.checklist]
        # Hard safety: never unlock large-motion host paths from this reporter.
        payload["control_ready"] = False
        payload["motion_enabled"] = False
        payload["live_permit"] = None
        payload["formal_grasp_blocked_by"] = list(self.formal_grasp_blocked_by)
        return payload


def compute_formal_grasp_blocked_by(
    *,
    formal_grasp_entry_allowed: bool,
    dry_run_grasp_entry_ready: bool,
    arm_ok_live: bool,
    live_permit_valid: bool,
    vision_ready: bool | None,
    permit_eligible: bool | None,
    traj_ok: bool,
    arm_ok_dry: bool,
    dry_reachable: bool,
    dry_issuance_ok: bool,
) -> tuple[str, ...]:
    """Root-cause blockers for formal grasp entry (machine-readable).

    When dry-run software path is exhausted, the remaining blockers collapse to
    ``j6_j7_readonly`` + ``awaiting_live_arm`` (live Permit cannot exist without
    counts_as_live_valid ArmState). Never claims Goal complete.
    """
    if formal_grasp_entry_allowed:
        return ()
    if dry_run_grasp_entry_ready:
        blocked: list[str] = []
        if not arm_ok_live:
            blocked.append(FORMAL_BLOCK_J6J7_READONLY)
            blocked.append(FORMAL_BLOCK_AWAITING_LIVE_ARM)
        elif not live_permit_valid:
            blocked.append("awaiting_live_permit")
        return tuple(blocked)

    blocked = []
    if vision_ready is not True:
        blocked.append("awaiting_vision_pre_grasp_ready")
    if permit_eligible is not True:
        blocked.append("awaiting_permit_eligible")
    if not traj_ok:
        blocked.append("awaiting_plan_bundle_trajectory_hash")
    if not arm_ok_dry:
        blocked.append("awaiting_arm_state_device_id")
    if not dry_reachable or not dry_issuance_ok:
        blocked.append("awaiting_dry_run_issuance")
    # Live arm hard-block still applies even before dry-run is ready.
    blocked.append(FORMAL_BLOCK_J6J7_READONLY)
    blocked.append(FORMAL_BLOCK_AWAITING_LIVE_ARM)
    return tuple(blocked)


def build_live_permit_path(
    *,
    dry_probe: dict[str, Any] | None,
    arm_ok_live: bool,
    live_permit_valid: bool,
    formal_grasp_blocked_by: tuple[str, ...],
) -> dict[str, Any]:
    """Summarize how far the live Permit software path reached (no forge)."""
    issuance = (dry_probe or {}).get("issuance_diagnostic") or {}
    fields_complete = issuance.get("issuance_fields_complete") is True
    gate_ok = issuance.get("gate_accepts_draft") is True
    if live_permit_valid and arm_ok_live:
        status = "live_permit_validated"
    elif fields_complete and gate_ok:
        status = "software_exhausted_awaiting_live_arm"
    elif issuance.get("issuance_attempted"):
        status = str(issuance.get("live_permit_path_status") or "issuance_incomplete")
    else:
        status = "not_probed"
    blocked = list(issuance.get("blocked_by") or formal_grasp_blocked_by)
    if not blocked and status == "software_exhausted_awaiting_live_arm":
        blocked = list(FORMAL_PERMIT_BLOCKED_BY_LIVE_ARM)
    return {
        "status": status,
        "executable": False,
        "live_permit": None,
        "issuance_fields_complete_under_mock": fields_complete,
        "gate_accepts_dry_run_draft": gate_ok if issuance else None,
        "required_fields": list(LIVE_PERMIT_REQUIRED_FIELDS),
        "arm_state_dependency": (
            "Permit.device_id must match counts_as_live_valid ArmState "
            "(source=real + validity=VALID + seven finite q_rad); "
            "J6/J7 lack audited readonly position query"
        ),
        "blocked_by": blocked,
        "hard_block_id": J6J7_HARD_BLOCK_ID,
        "never_forges_live_permit": True,
        "never_raises_control_ready": True,
    }


def _item(
    item_id: str,
    status: str,
    *,
    blocking: bool,
    category: str,
    detail: str,
    owner: str,
) -> ChecklistItem:
    return ChecklistItem(
        id=item_id,
        status=status,
        blocking=blocking,
        category=category,
        detail=detail,
        owner=owner,
    )


def _unwrap_arm_state(arm_state: dict[str, Any] | None) -> dict[str, Any] | None:
    """Accept raw ArmState or recorded / live-or-recorded wrappers."""
    unwrapped = unwrap_arm_state(arm_state)
    if unwrapped is not None:
        return unwrapped  # type: ignore[return-value]
    if not isinstance(arm_state, dict):
        return None
    return arm_state


def _validate_live_permit(
    *,
    live_permit: dict[str, Any],
    arm_state: dict[str, Any],
    plan_bundle: dict[str, Any] | None,
    diagnostic_permit: dict[str, Any] | None,
    config_path: str | Path,
) -> tuple[bool, str]:
    """Validate a claimed live Permit against OfflineSafetyGate + live arm.

    Returns (ok, detail). Never invents fields; fails closed on mismatch.
    """
    arm_class = classify_arm_state(arm_state)
    if not arm_class.get("counts_as_live_valid"):
        return False, (
            "live Permit validation requires counts_as_live_valid "
            f"(source={arm_state.get('source')!r} validity={arm_state.get('validity')!r} "
            f"blockers={arm_class.get('blockers')})"
        )
    required = (
        "device_id",
        "trajectory_hash",
        "config_hash",
        "calibration_hash",
        "scene_version",
        "valid_until_host_monotonic_s",
    )
    missing = [k for k in required if live_permit.get(k) in (None, "")]
    if missing:
        return False, f"live Permit missing fields: {missing}"

    traj = None
    if plan_bundle is not None:
        traj = plan_bundle.get("trajectory_hash") or (plan_bundle.get("trajectory") or {}).get(
            "hash"
        )
    if traj and str(live_permit.get("trajectory_hash")) != str(traj):
        return False, "live Permit.trajectory_hash != PlanBundle.trajectory_hash"

    if str(live_permit.get("device_id")) != str(arm_state.get("device_id")):
        return False, "live Permit.device_id != ArmState.device_id"

    hashes = _context_hashes_from_diagnostic(diagnostic_permit)
    config_hash = live_permit.get("config_hash") or hashes.get("config_hash")
    calibration_hash = live_permit.get("calibration_hash") or hashes.get("calibration_hash")
    scene_version = live_permit.get("scene_version") or hashes.get("scene_version")
    if not all((config_hash, calibration_hash, scene_version)):
        return False, "cannot validate live Permit without config/calibration/scene hashes"

    config = load_config(config_path)
    gate = OfflineSafetyGate(max_age_s=float(config["task"]["max_observation_age_s"]))
    now_s = float(arm_state.get("host_receive_stamp") or 0.0)
    try:
        gate.check_step_evidence(
            StepEvidence(
                feedback=arm_state,  # type: ignore[arg-type]
                calibration_valid=True,
                trajectory_hash=str(live_permit["trajectory_hash"]),
                permit=live_permit,  # type: ignore[arg-type]
            ),
            now_s=now_s,
            clock_domain=str(arm_state.get("clock_domain") or ""),
            epoch=str(arm_state.get("epoch") or ""),
            device_id=str(arm_state.get("device_id") or ""),
            config_hash=str(config_hash),
            calibration_hash=str(calibration_hash),
            scene_version=str(scene_version),
        )
    except (ValueError, TypeError, KeyError) as exc:
        return False, f"OfflineSafetyGate rejected live Permit: {exc}"
    return True, "live Permit validated by OfflineSafetyGate against live ArmState"


def probe_dry_run_arm_disabled(
    *,
    config_path: str | Path = "config/offline_task.yaml",
    diagnostic_permit: dict[str, Any] | None = None,
    plan_bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Reachability + issuance diagnostic for dry-run / arm-disabled path.

    Instantiates MockArm + OfflineSafetyGate. Exercises:
      1) reject step without permit
      2) dry-run issuance diagnostic (executable=false)
      3) plumbing self-check with labeled probe trajectory hash

    Never raises control_ready, never invents a formal PlanBundle hash,
    never opens CAN.
    """
    config = load_config(config_path)
    project = config.get("project") or {}
    dry_ok = project.get("dry_run") is True and project.get("environment") == "offline"

    arm = MockArm((0.0,) * 7, device_id="mock-arm-host-checklist")
    gate = OfflineSafetyGate(max_age_s=float(config["task"]["max_observation_age_s"]))

    class _MockPort:
        backend = "mock"
        hardware_enabled = False

    port = _MockPort()
    gate_config_ok = False
    gate_config_error: str | None = None
    try:
        if config["project"] != {"dry_run": True, "environment": "offline"}:
            raise ValueError("offline dry_run configuration required")
        if getattr(port, "backend", None) != "mock" or getattr(port, "hardware_enabled", None) is not False:
            raise ValueError("real/device adapters are not accepted by offline executor")
        gate_config_ok = True
    except ValueError as exc:
        gate_config_error = str(exc)

    state = arm.read_state()
    permit_reject_ok = False
    permit_reject_detail: str | None = None
    try:
        gate.check_step_evidence(
            StepEvidence(
                feedback=state,
                calibration_valid=True,
                trajectory_hash="unissued",
                permit=None,
            ),
            now_s=state["host_receive_stamp"],
            clock_domain=state["clock_domain"],
            epoch=state["epoch"],
            device_id=state["device_id"],
            config_hash="mock-config",
            calibration_hash="mock-calibration",
            scene_version="mock-scene",
        )
    except ValueError as exc:
        permit_reject_ok = "permit" in str(exc).lower()
        permit_reject_detail = str(exc)

    hashes = _context_hashes_from_diagnostic(diagnostic_permit)
    traj = None
    if plan_bundle is not None:
        traj = plan_bundle.get("trajectory_hash") or (plan_bundle.get("trajectory") or {}).get("hash")
    issuance = gate.issue_dry_run_diagnostic(
        arm=arm,
        config_hash=hashes.get("config_hash"),
        calibration_hash=hashes.get("calibration_hash"),
        scene_version=hashes.get("scene_version"),
        trajectory_hash=str(traj) if traj else None,
        run_plumbing_self_check=True,
    )

    plumbing = issuance.get("plumbing_self_check") or {}
    reachable = bool(
        dry_ok
        and gate_config_ok
        and arm.hardware_enabled is False
        and permit_reject_ok
        and issuance.get("issuance_attempted") is True
        and plumbing.get("gate_accepts_complete_dry_run_permit") is True
    )

    return {
        "schema_version": DRY_RUN_PROBE_SCHEMA,
        "reachable": reachable,
        "config_path": str(config_path).replace("\\", "/"),
        "project": {"dry_run": project.get("dry_run"), "environment": project.get("environment")},
        "offline_dry_run_config_ok": dry_ok,
        "offline_gate_port_check_ok": gate_config_ok,
        "offline_gate_port_check_error": gate_config_error,
        "mock_arm": {
            "backend": arm.backend,
            "hardware_enabled": arm.hardware_enabled,
            "device_id": state["device_id"],
        },
        "step_without_permit_rejected": permit_reject_ok,
        "step_without_permit_detail": permit_reject_detail,
        "issuance_diagnostic": issuance,
        "control_ready": False,
        "motion_enabled": False,
        "commands_sent": 0,
        "can_opened": False,
        "usage": [
            "Dry-run / arm-disabled path is OfflineSafetyGate + MockArm only.",
            "Issuance diagnostic is executable=false; live_permit stays null.",
            "This probe does not raise control_ready or invent a PlanBundle trajectory_hash.",
            "host_monitor --enable-motion is a separate live host path (main branch).",
        ],
    }


def evaluate_host_control_readiness(
    *,
    pre_grasp_gaps: dict[str, Any] | None = None,
    diagnostic_permit: dict[str, Any] | None = None,
    plan_bundle: dict[str, Any] | None = None,
    arm_state: dict[str, Any] | None = None,
    live_permit: dict[str, Any] | None = None,
    host_monitor_snapshot: dict[str, Any] | None = None,
    operator_policy_attest: HostPolicyAttest | dict[str, Any] | str | Path | None = None,
    config_path: str | Path | None = None,
    probe_dry_run: bool = False,
    rest_state_capture: bool | None = None,
) -> HostControlReadiness:
    """Build a machine-readable host/safety checklist against current evidence."""
    gaps = pre_grasp_gaps or {}
    diag = diagnostic_permit or gaps.get("diagnostic_permit") or {}
    vision_ready = gaps.get("vision_pre_grasp_ready")
    if vision_ready is None:
        vision_ready = diag.get("vision_pre_grasp_ready")
    permit_eligible = gaps.get("permit_eligible")
    if permit_eligible is None:
        permit_eligible = diag.get("permit_eligible")

    cfg = config_path or "config/offline_task.yaml"
    rest_gate_enabled = (
        bool(rest_state_capture)
        if rest_state_capture is not None
        else is_rest_state_capture_enabled()
    )
    rest_gate = rest_state_capture_gate_report(enabled=rest_gate_enabled)

    if isinstance(operator_policy_attest, HostPolicyAttest):
        attest = operator_policy_attest
    elif isinstance(operator_policy_attest, (str, Path)):
        attest = load_host_policy_attest(operator_policy_attest)
    elif isinstance(operator_policy_attest, dict):
        attested = operator_policy_attest.get("attested") is True or (
            operator_policy_attest.get("operator_attest_control_ready") is True
        )
        attest = HostPolicyAttest(
            schema_version=ATTEST_SCHEMA,
            attested=bool(attested),
            operator=(
                str(operator_policy_attest["operator"])
                if operator_policy_attest.get("operator")
                else None
            ),
            evidence_ref=(
                str(operator_policy_attest["evidence_ref"])
                if operator_policy_attest.get("evidence_ref")
                else None
            ),
            notes=str(operator_policy_attest.get("notes") or ""),
            control_ready=False,
            motion_enabled=False,
            path=None,
        )
    else:
        attest = empty_attest()

    items: list[ChecklistItem] = []

    # --- upstream vision / diagnostic eligibility ---
    if vision_ready is True:
        items.append(
            _item(
                "vision_pre_grasp_ready",
                "PASS",
                blocking=False,
                category="software",
                detail="vision_pre_grasp_ready=true in pre_grasp evidence",
                owner="V / pre_grasp_gates",
            )
        )
    elif vision_ready is False:
        items.append(
            _item(
                "vision_pre_grasp_ready",
                "FAIL",
                blocking=True,
                category="software",
                detail="vision_pre_grasp_ready=false; host enable blocked upstream",
                owner="V / pre_grasp_gates",
            )
        )
    else:
        items.append(
            _item(
                "vision_pre_grasp_ready",
                "UNKNOWN",
                blocking=True,
                category="software",
                detail="vision_pre_grasp_ready not provided; pass --pre-grasp-gaps",
                owner="operator / V",
            )
        )

    if permit_eligible is True:
        items.append(
            _item(
                "permit_eligible_diagnostic",
                "PASS",
                blocking=False,
                category="software",
                detail="diagnostic permit_eligible=true (not a live Permit)",
                owner="pre_grasp_gates diagnostic",
            )
        )
    elif permit_eligible is False:
        items.append(
            _item(
                "permit_eligible_diagnostic",
                "FAIL",
                blocking=True,
                category="software",
                detail="permit_eligible=false; evidence incomplete for live assessment",
                owner="pre_grasp_gates diagnostic",
            )
        )
    else:
        items.append(
            _item(
                "permit_eligible_diagnostic",
                "UNKNOWN",
                blocking=False,
                category="software",
                detail="permit_eligible not provided",
                owner="M / pre_grasp_gates",
            )
        )

    # --- PlanBundle / trajectory_hash ---
    traj = None
    if plan_bundle is not None:
        traj = plan_bundle.get("trajectory_hash") or (plan_bundle.get("trajectory") or {}).get("hash")
    diag_traj = ((diag.get("live_permit_field_status") or {}).get("trajectory_hash") or {}).get("status")
    if traj:
        items.append(
            _item(
                "plan_bundle_trajectory_hash",
                "PASS",
                blocking=False,
                category="software",
                detail=f"trajectory_hash present: {traj}",
                owner="M planning",
            )
        )
        traj_ok = True
    else:
        items.append(
            _item(
                "plan_bundle_trajectory_hash",
                "MISSING",
                blocking=True,
                category="software",
                detail=(
                    f"no PlanBundle trajectory_hash on host path "
                    f"(diagnostic={diag_traj or 'n/a'}); do not invent"
                ),
                owner="M planning",
            )
        )
        traj_ok = False

    # --- ArmState.device_id (recorded OK for dry-run; live VALID required for formal) ---
    arm_state = _unwrap_arm_state(arm_state)
    arm_feedback = classify_arm_state(arm_state)
    arm_device = arm_feedback.get("device_id")
    arm_source = arm_feedback.get("source")
    diag_arm = ((diag.get("live_permit_field_status") or {}).get("device_id") or {}).get("status")
    arm_ok_dry = bool(
        arm_device and arm_source in {"mock", "real", "recorded"}
    )
    # Live formal path: source=real AND validity=VALID AND seven finite joints.
    # Rest drafts may be structurally counts_as_live_valid when the research gate
    # is open, but Rest ≠ audited J6/J7 readonly — never auto-count as formal live.
    rest_draft = is_rest_state_capture_draft(arm_state)
    arm_structurally_live_valid = arm_feedback.get("counts_as_live_valid") is True
    arm_ok_live = arm_structurally_live_valid and not rest_draft
    if arm_ok_dry:
        items.append(
            _item(
                "arm_state_device_id",
                "PASS",
                blocking=False,
                category="software",
                detail=(
                    f"ArmState.device_id={arm_device} source={arm_source} "
                    f"validity={arm_feedback.get('validity')} "
                    f"(recorded/mock ≠ live VALID)"
                ),
                owner="A / arm adapter",
            )
        )
    else:
        items.append(
            _item(
                "arm_state_device_id",
                "MISSING",
                blocking=True,
                category="software",
                detail=(
                    "fresh ArmState.device_id missing "
                    f"(diagnostic={diag_arm or 'n/a'}; camera SN is not arm device_id)"
                ),
                owner="A / arm adapter",
            )
        )

    if arm_ok_live:
        items.append(
            _item(
                "live_valid_arm_state",
                "PASS",
                blocking=False,
                category="software",
                detail=(
                    f"live VALID ArmState.source=real device_id={arm_device} "
                    f"counts_as_live_valid=true"
                ),
                owner="A / ArmStateReader",
            )
        )
    else:
        source_kind = arm_feedback.get("source_kind") or "missing"
        blockers = list(arm_feedback.get("blockers") or [])
        if rest_draft:
            live_status = "POLICY_HOLD"
            live_detail = (
                "Rest-state-capture draft is structurally live VALID research-only; "
                "does not count as audited J6/J7 readonly for formal grasp "
                f"(hard_block=j6_j7_no_audited_readonly_position_query; "
                f"rest_state_capture_enabled={rest_gate_enabled}; "
                f"structural_counts_as_live_valid={arm_structurally_live_valid})"
            )
        elif source_kind == "recorded":
            live_status = "MISSING"
            live_detail = (
                "recorded ArmState/device_id binding present but does not count as "
                "live VALID "
                f"(hard_block=j6_j7_no_audited_readonly_position_query); "
                f"blockers={blockers}"
            )
        elif source_kind == "mock":
            live_status = "MISSING"
            live_detail = (
                "MockArm VALID is dry-run only "
                f"(hard_block=j6_j7_no_audited_readonly_position_query); "
                f"blockers={blockers}"
            )
        elif source_kind == "live_real":
            live_status = "FAIL"
            live_detail = (
                "live ArmStateReader sample present but not VALID "
                f"(hard_block=j6_j7_no_audited_readonly_position_query; "
                f"typically J6/J7 missing); blockers={blockers}; "
                f"reason={arm_feedback.get('reason')}"
            )
        else:
            live_status = "MISSING"
            live_detail = (
                "fresh VALID live ArmState missing "
                f"(hard_block=j6_j7_no_audited_readonly_position_query; "
                f"source_kind={source_kind}; blockers={blockers})"
            )
        items.append(
            _item(
                "live_valid_arm_state",
                live_status,
                blocking=True,
                category="software",
                detail=live_detail,
                owner="A / ArmStateReader",
            )
        )

    items.append(
        _item(
            "rest_state_capture_gate",
            "PASS" if rest_gate_enabled else "POLICY_HOLD",
            blocking=False,
            category="host_policy",
            detail=(
                "rest_state_capture research gate "
                f"available={rest_gate['rest_state_capture_available']} "
                f"enabled={rest_gate_enabled} "
                f"blocked_unless_rest_attested="
                f"{rest_gate['blocked_unless_rest_attested']}; "
                "default false; CI never auto Rest; loss-of-hold ≠ trajectory; "
                "does not raise formal_grasp_entry_allowed / control_ready"
            ),
            owner="A / rest_state_capture",
        )
    )

    # --- live Permit (never forge; validate if provided) ---
    live_permit_valid = False
    live_permit_detail = (
        "contracts.Permit is null; only D/M SafetyGate may issue at execution"
    )
    live_permit_status = "MISSING"
    if live_permit is not None:
        if not isinstance(live_permit, dict):
            live_permit_status = "FAIL"
            live_permit_detail = "live_permit input is not a dict; refuse"
        elif arm_state is None or not arm_ok_live:
            live_permit_status = "FAIL"
            live_permit_detail = (
                "non-null live_permit without live VALID ArmState; refuse elevation "
                "(do not treat dry-run draft as live)"
            )
        else:
            ok, detail = _validate_live_permit(
                live_permit=live_permit,
                arm_state=arm_state,
                plan_bundle=plan_bundle,
                diagnostic_permit=diag if isinstance(diag, dict) else None,
                config_path=cfg,
            )
            if ok:
                live_permit_valid = True
                live_permit_status = "PASS"
                live_permit_detail = detail
            else:
                live_permit_status = "FAIL"
                live_permit_detail = detail
    else:
        field_status = (diag.get("live_permit_field_status") or {}) if diag else {}
        if field_status:
            hints = ", ".join(
                f"{key}:{(value or {}).get('status')}"
                for key, value in field_status.items()
            )
            live_permit_detail = (
                "contracts.Permit is null; only D/M SafetyGate may issue at execution. "
                f"diagnostic field hints={{{hints}}}"
            )
    items.append(
        _item(
            "live_permit",
            live_permit_status,
            blocking=True,
            category="live_permit",
            detail=live_permit_detail,
            owner="D/M SafetyGate",
        )
    )

    # --- offline dry_run / arm-disabled path + issuance diagnostic ---
    dry_probe: dict[str, Any] | None = None
    dry_issuance_ok = False
    dry_reachable = False
    if probe_dry_run:
        dry_probe = probe_dry_run_arm_disabled(
            config_path=cfg,
            diagnostic_permit=diag if isinstance(diag, dict) else None,
            plan_bundle=plan_bundle,
        )
        issuance = dry_probe.get("issuance_diagnostic") or {}
        plumbing = issuance.get("plumbing_self_check") or {}
        missing_fields = list(issuance.get("still_missing_fields") or [])
        dry_reachable = bool(dry_probe.get("reachable"))
        dry_issuance_ok = bool(
            issuance.get("issuance_fields_complete")
            and issuance.get("gate_accepts_draft") is True
        )
        if dry_reachable:
            detail = (
                "OfflineSafetyGate+MockArm reachable; hardware_enabled=false; "
                f"step_without_permit_rejected={dry_probe.get('step_without_permit_rejected')}; "
                f"issuance_fields_complete={issuance.get('issuance_fields_complete')}; "
                f"plumbing_ok={plumbing.get('gate_accepts_complete_dry_run_permit')}; "
                f"still_missing_fields={missing_fields}; "
                f"only_hw_policy_remaining={issuance.get('only_hardware_enable_and_policy_remaining')}"
            )
            dry_status = "PROBED"
        else:
            fail_reason = (
                dry_probe.get("offline_gate_port_check_error")
                or dry_probe.get("step_without_permit_detail")
                or "unknown"
            )
            detail = f"dry-run probe failed: {fail_reason}"
            dry_status = "FAIL"
        items.append(
            _item(
                "dry_run_arm_disabled_path",
                dry_status,
                blocking=False,
                category="dry_run",
                detail=detail,
                owner="execution / OfflineSafetyGate",
            )
        )
        items.append(
            _item(
                "dry_run_safety_gate_issuance",
                "PASS" if dry_issuance_ok else ("PROBED" if issuance.get("issuance_attempted") else "FAIL"),
                blocking=False,
                category="dry_run",
                detail=(
                    "dry-run issuance diagnostic executable=false; "
                    f"fields_complete={issuance.get('issuance_fields_complete')}; "
                    f"gate_accepts_draft={issuance.get('gate_accepts_draft')}; "
                    f"still_missing={missing_fields}; "
                    "live_permit remains null"
                ),
                owner="D/M OfflineSafetyGate.issue_dry_run_diagnostic",
            )
        )
    else:
        items.append(
            _item(
                "dry_run_arm_disabled_path",
                "UNKNOWN",
                blocking=False,
                category="dry_run",
                detail="not probed; pass --probe-dry-run-arm-disabled",
                owner="execution / OfflineSafetyGate",
            )
        )
        items.append(
            _item(
                "dry_run_safety_gate_issuance",
                "UNKNOWN",
                blocking=False,
                category="dry_run",
                detail="not probed; pass --probe-dry-run-arm-disabled",
                owner="D/M OfflineSafetyGate.issue_dry_run_diagnostic",
            )
        )

    # --- host_monitor motion path (optional snapshot; sources live on main) ---
    mon = host_monitor_snapshot or {}
    motion_process = mon.get("motion_process_enabled")
    session_open = mon.get("session_open")
    if motion_process is True:
        items.append(
            _item(
                "host_monitor_enable_motion",
                "PASS",
                blocking=False,
                category="actuator_operator",
                detail="host_monitor process reports motion_process_enabled=true",
                owner="host_monitor",
            )
        )
    elif motion_process is False:
        items.append(
            _item(
                "host_monitor_enable_motion",
                "POLICY_HOLD",
                blocking=True,
                category="actuator_operator",
                detail="host_monitor running without --enable-motion (default safe)",
                owner="operator / host_monitor",
            )
        )
    else:
        items.append(
            _item(
                "host_monitor_enable_motion",
                "MISSING",
                blocking=True,
                category="actuator_operator",
                detail=(
                    "no host_monitor snapshot; live motion_enabled requires "
                    "--enable-motion + READY + ENABLE (this branch may lack host_monitor sources)"
                ),
                owner="operator / host_monitor",
            )
        )

    if session_open is True:
        items.append(
            _item(
                "host_monitor_session_ready",
                "PASS",
                blocking=False,
                category="actuator_operator",
                detail="control session open (confirm=READY)",
                owner="operator / host_monitor",
            )
        )
    elif session_open is False:
        items.append(
            _item(
                "host_monitor_session_ready",
                "POLICY_HOLD",
                blocking=True,
                category="actuator_operator",
                detail="control session closed; open with confirm=READY before ENABLE",
                owner="operator / host_monitor",
            )
        )
    else:
        items.append(
            _item(
                "host_monitor_session_ready",
                "MISSING",
                blocking=True,
                category="actuator_operator",
                detail="session_open unknown (no host_monitor snapshot)",
                owner="operator / host_monitor",
            )
        )

    # --- gate ladder computation ---
    dry_run_grasp_entry_ready = bool(
        vision_ready is True
        and permit_eligible is True
        and traj_ok
        and arm_ok_dry
        and dry_reachable
        and dry_issuance_ok
    )
    formal_grasp_entry_allowed = bool(
        dry_run_grasp_entry_ready and live_permit_valid and arm_ok_live
    )
    # Prerequisites for a *future* dedicated host elevation path.
    # This reporter NEVER sets control_ready=true (large-motion safety).
    control_ready_prerequisites_met = bool(
        formal_grasp_entry_allowed and attest.attested is True
    )
    control_ready = False

    items.append(
        _item(
            "dry_run_grasp_entry_ready",
            "PASS" if dry_run_grasp_entry_ready else ("UNKNOWN" if not probe_dry_run else "FAIL"),
            blocking=False,
            category="dry_run",
            detail=(
                "dry-run full chain ready"
                if dry_run_grasp_entry_ready
                else (
                    "dry-run chain incomplete; need vision+eligible+traj+arm+issuance "
                    f"(reachable={dry_reachable}, issuance_ok={dry_issuance_ok}, probed={probe_dry_run})"
                )
            ),
            owner="host_control_readiness gate ladder",
        )
    )
    # Preview blocked_by so formal gate detail can cite root causes.
    formal_grasp_blocked_by_preview = compute_formal_grasp_blocked_by(
        formal_grasp_entry_allowed=formal_grasp_entry_allowed,
        dry_run_grasp_entry_ready=dry_run_grasp_entry_ready,
        arm_ok_live=arm_ok_live,
        live_permit_valid=live_permit_valid,
        vision_ready=vision_ready if isinstance(vision_ready, bool) else None,
        permit_eligible=permit_eligible if isinstance(permit_eligible, bool) else None,
        traj_ok=traj_ok,
        arm_ok_dry=arm_ok_dry,
        dry_reachable=dry_reachable,
        dry_issuance_ok=dry_issuance_ok,
    )
    items.append(
        _item(
            "formal_grasp_entry_gate",
            "PASS" if formal_grasp_entry_allowed else "POLICY_HOLD",
            blocking=True,
            category="live_permit",
            detail=(
                "formal_grasp_entry_allowed=true"
                if formal_grasp_entry_allowed
                else (
                    "formal entry held: requires dry_run_grasp_entry_ready + validated "
                    "live Permit + live VALID ArmState (source=real, validity=VALID); "
                    f"dry_run_ready={dry_run_grasp_entry_ready}, "
                    f"live_permit_valid={live_permit_valid}, live_arm={arm_ok_live}; "
                    f"blocked_by={list(formal_grasp_blocked_by_preview)}"
                )
            ),
            owner="host/safety gate ladder",
        )
    )

    # --- operator policy attest (default closed; never auto-opens) ---
    if attest.attested:
        items.append(
            _item(
                "operator_policy_attest_control_ready",
                "PASS",
                blocking=False,
                category="host_policy",
                detail=(
                    f"operator attest present (operator={attest.operator!r}); "
                    "prerequisite only — this reporter still holds control_ready=false "
                    "(large-motion safety; elevation deferred)"
                ),
                owner="operator / host_policy_attest",
            )
        )
    else:
        items.append(
            _item(
                "operator_policy_attest_control_ready",
                "POLICY_HOLD",
                blocking=True,
                category="host_policy",
                detail=(
                    "operator_policy_attest closed (attested=false/missing); "
                    "default-safe. Explicit --attested required before any future "
                    "host path may consider control_ready; this reporter never raises it"
                ),
                owner="operator / host_policy_attest",
            )
        )

    items.append(
        _item(
            "host_policy_control_ready",
            "POLICY_HOLD",
            blocking=True,
            category="host_policy",
            detail=(
                "control_ready held false by reporter hard safety "
                "(no large-motion unlock). prerequisites_met="
                f"{control_ready_prerequisites_met} "
                f"(formal={formal_grasp_entry_allowed}, attest={attest.attested}); "
                "elevation deferred to dedicated host path after V+M→main"
            ),
            owner="host/safety (reporter never raises)",
        )
    )

    items.append(
        _item(
            "host_policy_motion_enabled",
            "POLICY_HOLD",
            blocking=True,
            category="host_policy",
            detail=(
                "motion_enabled held false by default; live path needs "
                "host_monitor --enable-motion + READY/ENABLE; planning outputs stay false"
            ),
            owner="host/safety (this checklist never enables)",
        )
    )

    # live_valid_arm_state is a formal/live software gap, but recorded device_id
    # still clears the older arm_state_device_id software checklist item.
    software_missing = tuple(
        i.id
        for i in items
        if i.blocking
        and i.category == "software"
        and i.status in {"FAIL", "MISSING", "UNKNOWN"}
        and i.id != "live_valid_arm_state"
    )
    # Keep live VALID visible as a hard blocker without collapsing recorded PASS.
    live_arm_software_gap = tuple(
        i.id
        for i in items
        if i.id == "live_valid_arm_state"
        and i.blocking
        and i.status in {"FAIL", "MISSING", "UNKNOWN"}
    )
    field_missing = tuple(
        i.id
        for i in items
        if i.blocking
        and i.category in {"live_permit", "host_policy", "actuator_operator"}
        and i.status in {"FAIL", "MISSING", "POLICY_HOLD", "UNKNOWN"}
    )
    hard_blockers = tuple(
        {
            "id": i.id,
            "status": i.status,
            "category": i.category,
            "detail": i.detail,
            "owner": i.owner,
        }
        for i in items
        if i.blocking and i.status != "PASS"
    )

    # Reporter never raises control_ready → never "only operator enable remaining".
    only_operator = False

    formal_missing: list[str] = []
    if not dry_run_grasp_entry_ready:
        formal_missing.append("dry_run_grasp_entry_ready")
    if not live_permit_valid:
        formal_missing.append("live_contracts_Permit_validated")
    if not arm_ok_live:
        formal_missing.append("live_VALID_ArmState_source_real")

    control_missing: list[str] = []
    if not formal_grasp_entry_allowed:
        control_missing.append("formal_grasp_entry_allowed")
    if not attest.attested:
        control_missing.append("operator_policy_attest_control_ready")
    # Always: this reporter refuses elevation (large-motion safety).
    control_missing.append("reporter_hard_hold_no_large_motion_elevation")

    formal_grasp_blocked_by = formal_grasp_blocked_by_preview
    live_permit_path = build_live_permit_path(
        dry_probe=dry_probe,
        arm_ok_live=arm_ok_live,
        live_permit_valid=live_permit_valid,
        formal_grasp_blocked_by=formal_grasp_blocked_by,
    )

    gate_ladder = {
        "vision_pre_grasp_ready": vision_ready is True,
        "dry_run_grasp_entry_ready": dry_run_grasp_entry_ready,
        "formal_grasp_entry_allowed": formal_grasp_entry_allowed,
        "control_ready": False,
        "control_ready_prerequisites_met": control_ready_prerequisites_met,
        "reporter_never_raises_control_ready": True,
        "reporter_never_raises_motion_enabled": True,
        "definitions": dict(GATE_DEFINITIONS),
        "formal_grasp_entry_missing": formal_missing,
        "formal_grasp_blocked_by": list(formal_grasp_blocked_by),
        "control_ready_missing": control_missing,
        "can_enter_formal_grasp": formal_grasp_entry_allowed,
        "operator_enable_required_now": False,
        "live_valid_arm_gap": list(live_arm_software_gap),
        "arm_feedback_source_kind": arm_feedback.get("source_kind"),
        "counts_as_live_valid": arm_ok_live,
        "structural_counts_as_live_valid": arm_structurally_live_valid,
        "rest_state_capture_draft": rest_draft,
        "rest_state_capture_available": True,
        "rest_state_capture_enabled": rest_gate_enabled,
        "blocked_unless_rest_attested": rest_gate["blocked_unless_rest_attested"],
        "j6j7_readonly_position_hard_block": True,
        "j6j7_readonly_hard_block_id": J6J7_HARD_BLOCK_ID,
        "live_permit_path_status": live_permit_path.get("status"),
    }

    issuance_notes: list[str] = []
    if dry_probe and isinstance(dry_probe.get("issuance_diagnostic"), dict):
        issuance = dry_probe["issuance_diagnostic"]
        issuance_notes.append(
            "Dry-run SafetyGate issuance diagnostic attempted "
            f"(fields_complete={issuance.get('issuance_fields_complete')}; "
            f"still_missing_fields={list(issuance.get('still_missing_fields') or [])}; "
            f"only_hw_policy_remaining={issuance.get('only_hardware_enable_and_policy_remaining')}; "
            f"blocked_by={list(issuance.get('blocked_by') or [])}; "
            f"live_permit_path_status={issuance.get('live_permit_path_status')})."
        )

    notes = (
        "Gate ladder: vision_pre_grasp_ready → dry_run_grasp_entry_ready → "
        "formal_grasp_entry_allowed → control_ready (attest-gated; reporter hard-hold).",
        "dry_run_grasp_entry_ready may be true without live Permit or control_ready.",
        "formal_grasp_entry_allowed requires validated live Permit + counts_as_live_valid "
        "(source=real AND validity=VALID AND seven finite q_rad).",
        "recorded/mock ArmState.device_id ≠ live VALID; see checklist live_valid_arm_state "
        f"and arm_feedback (source_kind={arm_feedback.get('source_kind')}).",
        "control_ready ALWAYS false in this reporter (large-motion safety). "
        "Attest switch defaults closed and is never auto-opened; even attested, elevation deferred.",
        "motion_enabled ALWAYS false here; never unlocks host_monitor large-motion paths.",
        "Never invents live contracts.Permit or opens CAN.",
        "Dry-run probe uses OfflineSafetyGate + MockArm (hardware_enabled=False).",
        "ArmStateReader readonly path currently cannot satisfy all_seven_q_rad_finite (J6/J7).",
        f"hard_block={J6J7_HARD_BLOCK_ID} "
        "(docs/team/B/J6J7_READONLY_POSITION_HARD_BLOCK_20261110.md); "
        "no enable-motion / trajectory fallback; Rest research gate default-off.",
        f"rest_state_capture_available={rest_gate['rest_state_capture_available']}; "
        f"rest_state_capture_enabled={rest_gate_enabled}; "
        f"blocked_unless_rest_attested={rest_gate['blocked_unless_rest_attested']}; "
        "Rest draft never auto-raises formal_grasp_entry_allowed / control_ready.",
        f"formal_grasp_blocked_by={list(formal_grasp_blocked_by)}.",
        f"live_permit_path.status={live_permit_path.get('status')}.",
        f"can_enter_formal_grasp={formal_grasp_entry_allowed}; "
        f"control_ready_prerequisites_met={control_ready_prerequisites_met}.",
        *issuance_notes,
    )

    return HostControlReadiness(
        schema_version=SCHEMA,
        control_ready=False,
        motion_enabled=False,
        formal_grasp_entry_allowed=formal_grasp_entry_allowed,
        formal_grasp_ready=False,
        dry_run_grasp_entry_ready=dry_run_grasp_entry_ready,
        vision_pre_grasp_ready=vision_ready if isinstance(vision_ready, bool) else None,
        only_operator_enable_remaining=only_operator,
        needs_operator_physical_enable_now=False,
        needs_operator_physical_enable_before_real_motion=True,
        permit_eligible=permit_eligible if isinstance(permit_eligible, bool) else None,
        live_permit=None,  # never echo claimed live permit into durable readiness
        operator_policy_attest=attest.to_dict(),
        gate_ladder=gate_ladder,
        checklist=tuple(items),
        missing_software=software_missing,
        missing_field_or_operator=field_missing,
        hard_blockers=hard_blockers,
        formal_grasp_blocked_by=formal_grasp_blocked_by,
        live_permit_path=live_permit_path,
        dry_run_arm_disabled=dry_probe,
        arm_feedback=arm_feedback,
        elevation_conditions={
            "vision_pre_grasp_ready": ["evidence_gates_clear"],
            "dry_run_grasp_entry_ready": list(DRY_RUN_GRASP_ENTRY_CONDITIONS),
            "formal_grasp_entry_allowed": list(FORMAL_GRASP_ENTRY_CONDITIONS),
            "control_ready": list(CONTROL_READY_ELEVATION_CONDITIONS),
            "motion_enabled": list(MOTION_ENABLED_ELEVATION_CONDITIONS),
            "rest_state_capture": rest_gate,
            "code_refs": {
                "OfflineSafetyGate": "src/brick_stacking/execution/safety_gate.py",
                "OfflineSafetyGate.issue_dry_run_diagnostic": (
                    "src/brick_stacking/execution/safety_gate.py"
                ),
                "host_policy_attest": "src/brick_stacking/execution/host_policy_attest.py",
                "OfflineExecutionManager": "src/brick_stacking/execution/execution_manager.py",
                "MockArm.hardware_enabled": "src/brick_stacking/arm/adapter.py",
                "ArmStateReader": "src/brick_stacking/arm/state.py",
                "arm_state_validity": "src/brick_stacking/arm/arm_state_validity.py",
                "v2_wrist_readonly_hard_block": "src/brick_stacking/arm/v2_wrist_readonly.py",
                "rest_state_capture": "src/brick_stacking/arm/rest_state_capture.py",
                "config_loader_offline_only": "src/brick_stacking/runtime/config_loader.py",
                "ObservationBundle.control_ready": "Literal[False] in contracts",
                "host_monitor_motion": "tools/host_monitor on main (--enable-motion)",
            },
        },
        notes=notes,
    )
