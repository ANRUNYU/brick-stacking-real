"""Host/safety control_ready + motion_enabled checklist (report-only).

Evaluates elevation *conditions* without raising control_ready, without
enabling actuators, and without sending CAN. Dry-run / arm-disabled probing
uses OfflineSafetyGate + MockArm only (hardware_enabled=False).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from brick_stacking.arm.adapter import MockArm
from brick_stacking.execution.safety_gate import OfflineSafetyGate, StepEvidence
from brick_stacking.runtime.config_loader import load_config

SCHEMA = "host-control-readiness-0.1"
DRY_RUN_PROBE_SCHEMA = "host-dry-run-arm-disabled-0.1"


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
# control_ready. This module never performs the raise.
CONTROL_READY_ELEVATION_CONDITIONS = (
    "vision_pre_grasp_ready_or_evidence_gates_clear",
    "live_contracts_Permit_from_SafetyGate",
    "PlanBundle_trajectory_hash",
    "fresh_ArmState_device_id_matching_permit",
    "offline_dry_run_config_or_explicit_live_host_policy",
    "host_policy_decision_to_raise_control_ready",
)

# Conditions for motion_enabled (host_monitor / actuator path).
MOTION_ENABLED_ELEVATION_CONDITIONS = (
    "process_started_with_enable_motion",  # host_monitor --enable-motion
    "control_session_confirm_READY",
    "joint_confirm_ENABLE",
    "live_permit_and_control_ready_for_trajectory_path",
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
    only_operator_enable_remaining: bool
    needs_operator_physical_enable_now: bool
    needs_operator_physical_enable_before_real_motion: bool
    vision_pre_grasp_ready: bool | None
    permit_eligible: bool | None
    live_permit: Any
    checklist: tuple[ChecklistItem, ...]
    missing_software: tuple[str, ...]
    missing_field_or_operator: tuple[str, ...]
    hard_blockers: tuple[dict[str, Any], ...]
    dry_run_arm_disabled: dict[str, Any] | None
    elevation_conditions: dict[str, Any]
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["checklist"] = [asdict(item) for item in self.checklist]
        # Hard invariants — never elevate from this reporter.
        payload["control_ready"] = False
        payload["motion_enabled"] = False
        payload["formal_grasp_entry_allowed"] = False
        payload["formal_grasp_ready"] = False
        payload["live_permit"] = None
        return payload


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
        # Scene identity is not exercised here; only the offline dry_run port gate.
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
    config_path: str | Path | None = None,
    probe_dry_run: bool = False,
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

    # --- live Permit ---
    if live_permit is not None:
        items.append(
            _item(
                "live_permit",
                "FAIL",
                blocking=True,
                category="live_permit",
                detail="non-null live_permit passed into host checklist; refuse elevation",
                owner="host_control_readiness",
            )
        )
        live_permit_present = True
    else:
        live_permit_present = False
        field_status = (diag.get("live_permit_field_status") or {}) if diag else {}
        if field_status:
            hints = ", ".join(
                f"{key}:{ (value or {}).get('status') }"
                for key, value in field_status.items()
            )
            permit_detail = (
                "contracts.Permit is null; only D/M SafetyGate may issue at execution. "
                f"diagnostic field hints={{{hints}}}"
            )
        else:
            permit_detail = (
                "contracts.Permit is null; only D/M SafetyGate may issue at execution"
            )
        items.append(
            _item(
                "live_permit",
                "MISSING",
                blocking=True,
                category="live_permit",
                detail=permit_detail,
                owner="D/M SafetyGate",
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

    # --- ArmState.device_id ---
    # Accept either raw ArmState or recorded-arm-state-0.1 wrapper.
    if (
        isinstance(arm_state, dict)
        and arm_state.get("schema_version") == "recorded-arm-state-0.1"
        and isinstance(arm_state.get("arm_state"), dict)
    ):
        arm_state = arm_state["arm_state"]
    arm_device = None
    if arm_state is not None:
        arm_device = arm_state.get("device_id")
    diag_arm = ((diag.get("live_permit_field_status") or {}).get("device_id") or {}).get("status")
    if arm_device and arm_state and arm_state.get("source") in {"mock", "real", "recorded"}:
        items.append(
            _item(
                "arm_state_device_id",
                "PASS",
                blocking=False,
                category="software",
                detail=f"ArmState.device_id={arm_device} source={arm_state.get('source')}",
                owner="A / arm adapter",
            )
        )
        arm_ok = True
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
        arm_ok = False

    # --- offline dry_run / arm-disabled path + issuance diagnostic ---
    dry_probe: dict[str, Any] | None = None
    if probe_dry_run:
        dry_probe = probe_dry_run_arm_disabled(
            config_path=config_path or "config/offline_task.yaml",
            diagnostic_permit=diag if isinstance(diag, dict) else None,
            plan_bundle=plan_bundle,
        )
        issuance = dry_probe.get("issuance_diagnostic") or {}
        plumbing = issuance.get("plumbing_self_check") or {}
        missing_fields = list(issuance.get("still_missing_fields") or [])
        if dry_probe.get("reachable"):
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
                (
                    "PASS"
                    if issuance.get("issuance_fields_complete")
                    and issuance.get("gate_accepts_draft") is True
                    else "PROBED"
                    if issuance.get("issuance_attempted")
                    else "FAIL"
                ),
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

    # --- host policy: this module never raises control_ready ---
    items.append(
        _item(
            "host_policy_control_ready",
            "POLICY_HOLD",
            blocking=True,
            category="host_policy",
            detail=(
                "control_ready held false by host/safety checklist; "
                "ObservationBundle.control_ready is Literal[False]; "
                "OfflineExecutionManager refuses hardware adapters; "
                "no production host path on this branch raises control_ready=true"
            ),
            owner="host/safety (this checklist never raises)",
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

    software_missing = tuple(
        i.id
        for i in items
        if i.blocking and i.category == "software" and i.status in {"FAIL", "MISSING", "UNKNOWN"}
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

    # only_operator_enable_remaining: ALL software + live permit + host policy
    # prerequisites satisfied except the physical ENABLE step.
    # Today host_policy always holds → this stays false by design of this release.
    software_clear = (
        vision_ready is True
        and (permit_eligible is True or permit_eligible is None)
        and traj_ok
        and arm_ok
        and live_permit_present
        and not software_missing
    )
    # Host policy still refuses elevation → never "only operator left" from this tool.
    only_operator = False
    if software_clear and motion_process is True and session_open is True:
        # Even then, this checklist does not claim only-operator: live trajectory
        # path still needs an explicit host policy raise which we refuse.
        only_operator = False

    issuance_notes: list[str] = []
    if dry_probe and isinstance(dry_probe.get("issuance_diagnostic"), dict):
        issuance = dry_probe["issuance_diagnostic"]
        issuance_notes.append(
            "Dry-run SafetyGate issuance diagnostic attempted "
            f"(fields_complete={issuance.get('issuance_fields_complete')}; "
            f"still_missing_fields={list(issuance.get('still_missing_fields') or [])}; "
            f"only_hw_policy_remaining={issuance.get('only_hardware_enable_and_policy_remaining')})."
        )

    notes = (
        "This checklist reports host/safety elevation conditions only.",
        "Never sets control_ready=true or motion_enabled=true.",
        "Never issues live contracts.Permit or opens CAN.",
        "Dry-run probe uses OfflineSafetyGate + MockArm (hardware_enabled=False).",
        "Dry-run issuance is executable=false; plumbing self-check uses a labeled probe hash only.",
        "host_monitor motion path (main) is separate: --enable-motion → READY → ENABLE → MOVE.",
        "only_operator_enable_remaining stays false while host_policy holds control_ready down "
        "or PlanBundle / live Permit / ArmState are missing.",
        "Formal grasp: NO until live Permit + host policy raise + actuator enable.",
        *issuance_notes,
    )

    return HostControlReadiness(
        schema_version=SCHEMA,
        control_ready=False,
        motion_enabled=False,
        formal_grasp_entry_allowed=False,
        formal_grasp_ready=False,
        only_operator_enable_remaining=only_operator,
        needs_operator_physical_enable_now=False,
        needs_operator_physical_enable_before_real_motion=True,
        vision_pre_grasp_ready=vision_ready if isinstance(vision_ready, bool) else None,
        permit_eligible=permit_eligible if isinstance(permit_eligible, bool) else None,
        live_permit=None,
        checklist=tuple(items),
        missing_software=software_missing,
        missing_field_or_operator=field_missing,
        hard_blockers=hard_blockers,
        dry_run_arm_disabled=dry_probe,
        elevation_conditions={
            "control_ready": list(CONTROL_READY_ELEVATION_CONDITIONS),
            "motion_enabled": list(MOTION_ENABLED_ELEVATION_CONDITIONS),
            "code_refs": {
                "OfflineSafetyGate": "src/brick_stacking/execution/safety_gate.py",
                "OfflineSafetyGate.issue_dry_run_diagnostic": (
                    "src/brick_stacking/execution/safety_gate.py"
                ),
                "OfflineExecutionManager": "src/brick_stacking/execution/execution_manager.py",
                "MockArm.hardware_enabled": "src/brick_stacking/arm/adapter.py",
                "config_loader_offline_only": "src/brick_stacking/runtime/config_loader.py",
                "ObservationBundle.control_ready": "Literal[False] in contracts",
                "host_monitor_motion": "tools/host_monitor on main (--enable-motion)",
            },
        },
        notes=notes,
    )
