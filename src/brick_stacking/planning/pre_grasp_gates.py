"""Pre-grasp software gates and readiness reporting.

Evidence-only: never invents PASS, never raises control_ready, never emits permits
or motion commands. Missing evidence stays FAIL/UNKNOWN/BLOCKED with explicit gaps.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from brick_stacking.planning.yaw_policy import (
    normalize_yaw_policy,
    yaw_unknown_allowed_by_policy,
)


SCHEMA = "pre-grasp-readiness-0.1"

# Gate ids used by docs, CLI, and tests. Status values are never forged to PASS.
GATE_IDS = (
    "association",
    "hand_clear",
    "support_ok",
    "stable",
    "neighbors_unchanged",
    "yaw_bound",
    "xy_height_measured",
    "color_match",
    "reference_id",
    "expected_pose_adopted",
    "calibration_binding",
    "bundle_binding_clock",
    "m_context",
    "formal_verify_path",
    "shadow_inspection",
    "permit",
    "control_ready_policy",
)


@dataclass(frozen=True)
class GateResult:
    gate_id: str
    status: str  # PASS | FAIL | UNKNOWN | BLOCKED | POLICY_HOLD
    software_landed: bool
    field_or_human_required: bool
    blocking_for_formal_grasp: bool
    detail: str
    evidence_refs: tuple[str, ...] = ()
    owner_hint: str = ""


@dataclass(frozen=True)
class ReadinessReport:
    schema_version: str
    phase: str
    control_ready: bool
    motion_enabled: bool
    permit: Any
    formal_grasp_entry_allowed: bool
    evidence_gates_clear: bool
    # Vision/pre_grasp evidence only: never implies permit, control_ready, or CAN.
    vision_pre_grasp_ready: bool
    awaiting_m_permit: bool
    awaiting_actuator_enable: bool
    gates: tuple[GateResult, ...]
    missing_software: tuple[str, ...]
    missing_field_or_human: tuple[str, ...]
    consumer_reason_union: tuple[str, ...]
    formal_verdict_counts: dict[str, int]
    notes: tuple[str, ...]
    inputs: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["gates"] = [asdict(g) for g in self.gates]
        return out


def load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return __import__("json").loads(path.read_text(encoding="utf-8"))


def _handoff_rows(shadow: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not shadow:
        return []
    export = shadow.get("export") or {}
    return list(export.get("localized_review_handoffs") or [])


def _scene_consistent_indices(handoffs: list[dict[str, Any]]) -> list[int]:
    """Indices where monitor reached CONFIRMED (required_frames consecutive agree).

    Earlier WARMING_UP frames are expected non-candidates under required_frames>=2;
    they must not be forged to scene_consistent=true and must not block readiness
    once a later confirmed frame exists.
    """
    return [i for i, row in enumerate(handoffs) if row.get("scene_consistent") is True]


def _preferred_handoff(handoffs: list[dict[str, Any]]) -> dict[str, Any]:
    """Prefer the latest scene_consistent handoff; else first row (honest gap)."""
    consistent = [row for row in handoffs if row.get("scene_consistent") is True]
    if consistent:
        return consistent[-1]
    return handoffs[0] if handoffs else {}


def _consumption_reasons(
    shadow: dict[str, Any] | None,
    *,
    eligible_indices: list[int] | None = None,
) -> list[str]:
    if not shadow:
        return []
    rows = list(shadow.get("consumption") or [])
    if eligible_indices is None:
        selected = rows
    else:
        selected = [rows[i] for i in eligible_indices if 0 <= i < len(rows)]
        # No confirmed frame yet: keep full union so SCENE warmup gap stays visible.
        if not selected:
            selected = rows
    reasons: list[str] = []
    for row in selected:
        diagnostic = row.get("diagnostic") or {}
        reasons.extend(diagnostic.get("reasons") or [])
    return sorted(set(reasons))


def _eligible_consumption_counts(
    shadow: dict[str, Any] | None,
    eligible_indices: list[int],
) -> tuple[int, int, int]:
    """Return (ready_n, blocked_n, warmup_skipped) over scene_consistent frames only."""
    rows = list((shadow or {}).get("consumption") or [])
    if not eligible_indices:
        ready_n = sum(
            1
            for row in rows
            if (row.get("diagnostic") or {}).get("status") == "SHADOW_INSPECTION_READY"
        )
        blocked_n = sum(
            1 for row in rows if (row.get("diagnostic") or {}).get("status") == "BLOCKED"
        )
        return ready_n, blocked_n, 0
    eligible = [rows[i] for i in eligible_indices if 0 <= i < len(rows)]
    ready_n = sum(
        1
        for row in eligible
        if (row.get("diagnostic") or {}).get("status") == "SHADOW_INSPECTION_READY"
    )
    blocked_n = sum(
        1 for row in eligible if (row.get("diagnostic") or {}).get("status") == "BLOCKED"
    )
    return ready_n, blocked_n, max(0, len(rows) - len(eligible_indices))


def evaluate_pre_grasp_readiness(
    *,
    request: dict[str, Any] | None = None,
    shadow_report: dict[str, Any] | None = None,
    association_record: dict[str, Any] | None = None,
    request_path: str | None = None,
    shadow_path: str | None = None,
    association_path: str | None = None,
) -> ReadinessReport:
    """Assemble gate status from adopted request + optional shadow/association artifacts."""
    req = request or {}
    handoffs = _handoff_rows(shadow_report)
    consistent_idx = _scene_consistent_indices(handoffs)
    first = _preferred_handoff(handoffs)
    reasons = _consumption_reasons(shadow_report, eligible_indices=consistent_idx)
    export = (shadow_report or {}).get("export") or {}
    verdict_counts = dict(export.get("verification_verdict_counts") or {})
    color_counts = dict(export.get("color_check_counts") or {})

    assoc_flag = bool(req.get("target_association_confirmed"))
    assoc_from_export = bool(export.get("target_association_confirmed"))
    assoc_record_ok = bool(
        association_record
        and association_record.get("target_association_confirmed") is True
        and association_record.get("operator_confirmed") is True
        and association_record.get("target_id")
        and association_record.get("reference_id")
    )
    association_effective = assoc_flag or assoc_from_export or assoc_record_ok

    def gate(
        gate_id: str,
        status: str,
        *,
        software: bool,
        field: bool,
        blocking: bool,
        detail: str,
        refs: tuple[str, ...] = (),
        owner: str = "",
    ) -> GateResult:
        return GateResult(
            gate_id=gate_id,
            status=status,
            software_landed=software,
            field_or_human_required=field,
            blocking_for_formal_grasp=blocking,
            detail=detail,
            evidence_refs=refs,
            owner_hint=owner,
        )

    gates: list[GateResult] = []

    # --- association ---
    if association_effective and assoc_record_ok:
        assoc_status = "PASS"
        assoc_detail = "operator association record present and matches target/reference"
    elif association_effective and not assoc_record_ok:
        assoc_status = "UNKNOWN"
        assoc_detail = (
            "association flag asserted (CLI/request/export) but durable operator "
            "association_confirm record missing"
        )
    else:
        assoc_status = "FAIL"
        assoc_detail = "target_association_confirmed is false; single VALID candidate is not enough"
    gates.append(
        gate(
            "association",
            assoc_status,
            software=True,
            field=True,
            blocking=True,
            detail=assoc_detail,
            refs=tuple(
                r
                for r in (
                    association_path,
                    (association_record or {}).get("evidence_ref"),
                )
                if r
            ),
            owner="operator + V export switch",
        )
    )

    # --- explicit evidence fields from handoff / request post_place ---
    post = req.get("post_place_evidence") or {}
    hand_clear = first.get("hand_clear", post.get("hand_clear"))
    support_ok = first.get("support_ok", post.get("support_ok"))
    stable = first.get("stable", post.get("stable"))
    neighbors = first.get("neighbors_unchanged", post.get("neighbors_unchanged"))

    for gid, value, note, pre_grasp_blocking in (
        (
            "hand_clear",
            hand_clear,
            "explicit bool required by consume_handoff; scene_consistent must not be copied",
            True,
        ),
        (
            "support_ok",
            support_ok,
            "explicit bool or leave UNKNOWN; not inferred from scene_consistent",
            False,
        ),
        (
            "stable",
            stable,
            "stability window required for post_place; tracked as pre_grasp evidence gap",
            False,
        ),
        (
            "neighbors_unchanged",
            neighbors,
            "explicit bool or UNKNOWN; not inferred",
            False,
        ),
    ):
        if isinstance(value, bool):
            st = "PASS" if value else "FAIL"
        else:
            st = "UNKNOWN"
        blocking = pre_grasp_blocking or value is False
        gates.append(
            gate(
                gid,
                st,
                software=True,
                field=True,
                blocking=blocking,
                detail=f"{note}; current={value!r}",
                owner="field evidence / M context",
            )
        )

    # --- yaw ---
    yaw = first.get("yaw_rad") or {}
    yaw_pol = normalize_yaw_policy(req.get("yaw_policy") or first.get("yaw_policy"))
    if yaw.get("status") == "MEASURED" and isinstance(yaw.get("value"), (int, float)):
        yaw_status, yaw_detail = "PASS", "yaw ErrorBound MEASURED"
        yaw_blocking = True
        yaw_field = False
    elif yaw_unknown_allowed_by_policy(yaw, yaw_pol):
        yaw_status, yaw_detail = (
            "PASS",
            "yaw UNKNOWN accepted under yaw_policy=symmetric_90_unbounded "
            "(90° cube; not MEASURED; no forged angle)",
        )
        yaw_blocking = False
        yaw_field = False
    else:
        yaw_status, yaw_detail = (
            "UNKNOWN",
            "yaw UNKNOWN (90° symmetry); declare yaw_policy=symmetric_90_unbounded "
            "or supply MEASURED bound — do not forge",
        )
        yaw_blocking = True
        yaw_field = True
    gates.append(
        gate(
            "yaw_bound",
            yaw_status,
            software=True,
            field=yaw_field,
            blocking=yaw_blocking,
            detail=yaw_detail,
            owner="V measurement policy / yaw_policy / operator orientation confirm",
        )
    )

    # --- xy/height ---
    xy = first.get("xy_m") or {}
    height = first.get("height_m") or {}
    xy_ok = xy.get("status") == "MEASURED" and height.get("status") == "MEASURED"
    gates.append(
        gate(
            "xy_height_measured",
            "PASS" if xy_ok else "UNKNOWN",
            software=True,
            field=False,
            blocking=not xy_ok,
            detail=(
                f"xy={xy.get('value')!r} status={xy.get('status')}; "
                f"height={height.get('value')!r} status={height.get('status')}"
                if handoffs
                else "no shadow handoff rows loaded"
            ),
            owner="V LocalizedReview vs adopted expectation",
        )
    )

    # --- color ---
    match_n = int(color_counts.get("MATCH") or 0)
    n_frames = int(export.get("n_frames") or 0)
    color_pass = n_frames > 0 and match_n == n_frames and not color_counts.get("MISMATCH")
    gates.append(
        gate(
            "color_match",
            "PASS" if color_pass else ("UNKNOWN" if not handoffs else "FAIL"),
            software=True,
            field=False,
            blocking=not color_pass,
            detail=f"color_check_counts={color_counts or '{}'}",
            owner="V color diagnostic (formal verdict separate)",
        )
    )

    # --- reference / expectation adoption ---
    ref_id = req.get("reference_id") or first.get("reference_id")
    gates.append(
        gate(
            "reference_id",
            "PASS" if ref_id else "FAIL",
            software=True,
            field=False,
            blocking=not bool(ref_id),
            detail=f"reference_id={ref_id!r}",
            owner="adopted request",
        )
    )
    formal = req.get("formal_verify_reference") or {}
    review = req.get("placement_review_reference") or {}
    expected_ok = (
        formal.get("expected_center_camera_m") is not None
        and review.get("expected_point_camera_m") is not None
        and formal.get("point_kind") == "model_center"
        and (review.get("point_kind") in (None, "visible_top_center"))
    )
    gates.append(
        gate(
            "expected_pose_adopted",
            "PASS" if expected_ok else "FAIL",
            software=True,
            field=False,
            blocking=not expected_ok,
            detail=f"request.status={req.get('status')!r}; formal/review expectations present={expected_ok}",
            owner="adopted request shadow",
        )
    )

    # --- calibration (parallel work) ---
    cal = req.get("calibration_hash") or first.get("calibration_hash")
    candidate = (req.get("calibration_candidate") or {}).get("status")
    cal_ok = bool(cal) and cal != "calibration_hash_unavailable"
    gates.append(
        gate(
            "calibration_binding",
            "PASS" if cal_ok else "BLOCKED",
            software=False,
            field=True,
            blocking=True,
            detail=(
                f"calibration_hash={cal!r}; candidate_status={candidate!r}. "
                "C35 fit-only sha is not an approved current binding."
            ),
            owner="calibration parallel agent / operator approve",
        )
    )

    # --- BundleBinding / clock ---
    clock_bound = first.get("clock_error_bound_s")
    clock_ref = first.get("error_bound_evidence_ref")
    binding_missing = "BUNDLE_BINDING_MISSING" in reasons or "TIMING_UNKNOWN_STALE_OR_FUTURE" in reasons
    clock_ok = (
        isinstance(clock_bound, (int, float))
        and clock_bound > 0
        and bool(clock_ref)
        and not binding_missing
    )
    gates.append(
        gate(
            "bundle_binding_clock",
            "PASS" if clock_ok else "BLOCKED",
            software=False,
            field=True,
            blocking=True,
            detail=(
                f"clock_error_bound_s={clock_bound!r}; evidence_ref={clock_ref!r}; "
                f"consumer_has_BUNDLE_BINDING_MISSING={('BUNDLE_BINDING_MISSING' in reasons)}"
            ),
            owner="clock/BundleBinding parallel agent",
        )
    )

    # --- M context ---
    m_missing = "M_CONTEXT_MISSING" in reasons or "M_TARGET_CONTEXT_MISMATCH" in reasons
    if shadow_report is None:
        m_status, m_ok = "UNKNOWN", False
        m_detail = "no shadow consumption loaded; M Context required for Inspection"
    elif m_missing:
        m_status, m_ok = "BLOCKED", False
        m_detail = "consume_handoff context=None or mismatch → M_CONTEXT_MISSING"
    else:
        m_status, m_ok = "PASS", True
        m_detail = "no M_CONTEXT_* reasons in consumer diagnostics"
    gates.append(
        gate(
            "m_context",
            m_status,
            software=True,
            field=False,
            blocking=not m_ok,
            detail=m_detail,
            owner="M Context construction (target_id/scope/hashes)",
        )
    )

    # --- formal verify path ---
    # Warmup frames stay UNKNOWN (reference_confirmed requires scene_consistent).
    # Gate only on scene_consistent frames; do not lower required_frames / forge confirm.
    evidence_rows = list(export.get("verification_evidence") or [])
    if consistent_idx and evidence_rows:
        confirmed_verdicts = [
            (evidence_rows[i] or {}).get("verdict")
            for i in consistent_idx
            if i < len(evidence_rows)
        ]
        pass_n = sum(1 for v in confirmed_verdicts if v == "PASS")
        unknown_n = sum(1 for v in confirmed_verdicts if v == "UNKNOWN")
        fail_n = sum(1 for v in confirmed_verdicts if v == "FAIL")
        formal_counts = {
            "PASS": pass_n,
            "UNKNOWN": unknown_n,
            "FAIL": fail_n,
            "warmup_skipped": max(0, len(handoffs) - len(consistent_idx)),
        }
    else:
        pass_n = int(verdict_counts.get("PASS") or 0)
        unknown_n = int(verdict_counts.get("UNKNOWN") or 0)
        fail_n = int(verdict_counts.get("FAIL") or 0)
        formal_counts = dict(verdict_counts)
    if not handoffs:
        formal_status = "UNKNOWN"
        formal_detail = "no verification_evidence loaded"
    elif pass_n > 0 and unknown_n == 0 and fail_n == 0:
        # Even if formal PASS appears, readiness still refuses control_ready elevation here.
        formal_status = "PASS"
        formal_detail = (
            f"scene_consistent_verdicts={formal_counts}; "
            f"raw_verdict_counts={verdict_counts} (position_only scope possible)"
        )
    else:
        formal_status = "UNKNOWN"
        formal_detail = (
            f"scene_consistent_verdicts={formal_counts}; "
            f"raw_verdict_counts={verdict_counts}; formal path not cleared"
        )
    gates.append(
        gate(
            "formal_verify_path",
            formal_status,
            software=True,
            field=False,
            blocking=formal_status != "PASS",
            detail=formal_detail,
            owner="verify_export + visual_transition.verify",
        )
    )

    # --- shadow inspection / permit / control_ready policy ---
    # Only scene_consistent frames are readiness candidates; WARMING_UP
    # SCENE_OR_RGBD_NOT_CONFIRMED is expected and skipped (not a safety relax).
    ready_n, blocked_n, warmup_skipped = _eligible_consumption_counts(
        shadow_report, consistent_idx
    )
    insp_ok = ready_n > 0 and blocked_n == 0 and bool(consistent_idx)
    gates.append(
        gate(
            "shadow_inspection",
            "PASS" if insp_ok else ("BLOCKED" if shadow_report else "UNKNOWN"),
            software=True,
            field=False,
            blocking=not insp_ok,
            detail=(
                f"shadow_inspection_ready={ready_n}; blocked={blocked_n}; "
                f"warmup_or_unconfirmed_skipped={warmup_skipped}; "
                f"scene_consistent_frames={len(consistent_idx)}; reasons={reasons}"
            ),
            owner="verify_handoff_consumer",
        )
    )
    permit = (shadow_report or {}).get("permit")
    if permit is None and shadow_report:
        # dig first consumption permit
        for c in shadow_report.get("consumption") or []:
            permit = (c.get("diagnostic") or {}).get("permit")
            break
    gates.append(
        gate(
            "permit",
            "POLICY_HOLD" if permit is None else "FAIL",
            software=True,
            field=False,
            blocking=True,
            detail="permit must remain null until every blocking gate clears; never forge",
            owner="M permit authority (not granted here)",
        )
    )
    # Hard policy: this module never allows control_ready true.
    cr_req = req.get("control_ready")
    cr_shadow = (shadow_report or {}).get("control_ready")
    cr_export = export.get("control_ready")
    if any(x is True for x in (cr_req, cr_shadow, cr_export)):
        cr_status, cr_detail = "FAIL", "control_ready unexpectedly true in inputs — refuse elevation"
    else:
        cr_status, cr_detail = (
            "POLICY_HOLD",
            "control_ready held false by policy until all blocking gates PASS",
        )
    gates.append(
        gate(
            "control_ready_policy",
            cr_status,
            software=True,
            field=False,
            blocking=True,
            detail=cr_detail,
            owner="safety policy",
        )
    )

    policy_ids = {"permit", "control_ready_policy"}
    evidence_blocking = [
        g for g in gates if g.blocking_for_formal_grasp and g.gate_id not in policy_ids
    ]
    evidence_clear = all(g.status == "PASS" for g in evidence_blocking)
    # Vision-side announce only: evidence clear ⇒ pre_grasp vision ready.
    # Does NOT equal formal grasp entry, permit, control_ready, or motion enable.
    vision_ready = evidence_clear
    # Hard hold: this reporter never authorizes formal grasp / control_ready / CAN.
    formal_allowed = False

    missing_software = tuple(
        g.gate_id
        for g in gates
        if g.blocking_for_formal_grasp and g.status != "PASS" and g.software_landed
    )
    missing_field = tuple(
        g.gate_id
        for g in gates
        if g.blocking_for_formal_grasp and g.status != "PASS" and g.field_or_human_required
    )

    notes = (
        "Readiness reports gaps only; does not grant permit or raise control_ready.",
        "Association CLI flag without durable operator record stays UNKNOWN.",
        "Calibration binding and BundleBinding/clock are parallel dependencies.",
        "hand_clear/support/stable/neighbors are never inferred from scene_consistent.",
        "yaw_policy=symmetric_90_unbounded accepts UNKNOWN yaw for grasp-approach; never forges MEASURED.",
        "vision_pre_grasp_ready mirrors evidence_gates_clear; it is NOT formal_grasp_entry_allowed.",
        "formal_grasp_entry_allowed / control_ready / permit / motion_enabled stay false here by design.",
        "Remaining formal-entry hard holds: M permit authority + host/safety control_ready + actuator enable.",
        "Readiness adopts only scene_consistent frames; WARMING_UP SCENE_OR_RGBD_NOT_CONFIRMED is skipped, not forged.",
    )
    return ReadinessReport(
        schema_version=SCHEMA,
        phase="pre_grasp",
        control_ready=False,
        motion_enabled=False,
        permit=None,
        formal_grasp_entry_allowed=formal_allowed,
        evidence_gates_clear=evidence_clear,
        vision_pre_grasp_ready=vision_ready,
        awaiting_m_permit=True,
        awaiting_actuator_enable=True,
        gates=tuple(gates),
        missing_software=missing_software,
        missing_field_or_human=missing_field,
        consumer_reason_union=tuple(reasons),
        formal_verdict_counts=verdict_counts,
        notes=notes,
        inputs={
            "request_path": request_path,
            "shadow_path": shadow_path,
            "association_path": association_path,
            "request_status": req.get("status"),
            "target_id": req.get("target_id"),
            "reference_id": req.get("reference_id"),
        },
    )


def association_switch_payload(
    *,
    target_id: str,
    reference_id: str,
    region_id: str,
    slot_id: str | None,
    operator: str,
    evidence_ref: str,
    notes: str = "",
    confirmed: bool = True,
) -> dict[str, Any]:
    """Build a durable association confirm record (switch). Never touches motion."""
    if confirmed and not all((target_id, reference_id, region_id, operator, evidence_ref)):
        raise ValueError("confirmed association requires target/reference/region/operator/evidence_ref")
    return {
        "schema_version": "association-confirm-switch-0.1",
        "target_association_confirmed": bool(confirmed),
        "operator_confirmed": bool(confirmed),
        "target_id": target_id,
        "slot_id": slot_id,
        "region_id": region_id,
        "reference_id": reference_id,
        "operator": operator,
        "evidence_ref": evidence_ref,
        "notes": notes,
        "control_ready": False,
        "motion_enabled": False,
        "permit": None,
        "usage": [
            "Pass to tools/pre_grasp_readiness.py --association-record",
            "For shadow export only: tools/slot_shadow_pipeline.py --association-confirmed",
            "Does not mutate adopted request; does not raise control_ready",
        ],
    }


def evidence_gap_report(readiness: ReadinessReport) -> dict[str, Any]:
    """Compact gap list for operators and CI."""
    gaps = []
    for g in readiness.gates:
        if g.status == "PASS":
            continue
        gaps.append(
            {
                "gate_id": g.gate_id,
                "status": g.status,
                "blocking": g.blocking_for_formal_grasp,
                "field_or_human_required": g.field_or_human_required,
                "detail": g.detail,
                "owner_hint": g.owner_hint,
            }
        )
    return {
        "schema_version": "pre-grasp-evidence-gaps-0.1",
        "formal_grasp_entry_allowed": False,
        "control_ready": False,
        "motion_enabled": False,
        "permit": None,
        "evidence_gates_clear": readiness.evidence_gates_clear,
        "vision_pre_grasp_ready": readiness.vision_pre_grasp_ready,
        "awaiting_m_permit": readiness.awaiting_m_permit,
        "awaiting_actuator_enable": readiness.awaiting_actuator_enable,
        "blocking_gaps": [g for g in gaps if g["blocking"]],
        "nonblocking_gaps": [g for g in gaps if not g["blocking"]],
        "consumer_reason_union": list(readiness.consumer_reason_union),
        "missing_software": list(readiness.missing_software),
        "missing_field_or_human": list(readiness.missing_field_or_human),
        "notes": list(readiness.notes),
    }
