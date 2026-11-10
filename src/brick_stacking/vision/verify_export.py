"""Build verify / placement-review handoff records from ObservationBundle rows.

Does not invent target association, support/stable/hand-clear evidence, yaw, or
calibration hashes. Does not raise control_ready.

Point semantics (M ACK be50b37):
- LocalizedReview / placement_review → visible_top_center
- Formal VisualSample / verify → model_center
Never silently fall back between the two.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

from brick_stacking.verification.visual_transition import (
    VerificationRequest,
    VisualSample,
    verify,
)
from brick_stacking.planning.yaw_policy import normalize_yaw_policy

SCHEMA = "v-verify-field-handoff-0.2"
OPTICAL_FRAME_PREFIX = "camera_"
OPTICAL_FRAME_SUFFIX = "_color_optical_frame"
POINT_KIND_MODEL_CENTER = "model_center"
POINT_KIND_VISIBLE_TOP_CENTER = "visible_top_center"
CALIBRATION_SENTINEL = "calibration_hash_unavailable"


@dataclass(frozen=True)
class ErrorBoundDict:
    value: float | None
    bound: float | None
    status: str  # MEASURED | UNKNOWN


@dataclass(frozen=True)
class LocalizedReviewHandoff:
    """V→M side-car aligned with M LocalizedReviewEvidence fields."""
    schema_version: str
    target_id: str | None
    slot_id: str | None
    region_id: str | None
    scope: str
    sample_id: str
    observation_id: str | None
    frame_id: str
    point_kind: str | None
    formal_verify_point_kind: str
    target_association_confirmed: bool
    reference_id: str | None
    xy_m: ErrorBoundDict
    height_m: ErrorBoundDict
    yaw_rad: ErrorBoundDict
    support_ok: bool | None
    stable: bool | None
    hand_clear: bool | None
    neighbors_unchanged: bool | None
    color: str | None
    expected_color: str | None
    color_check: str  # MATCH | MISMATCH | UNKNOWN
    scene_consistent: bool | None
    profile_hash: str | None
    calibration_hash: str | None
    calibration_candidate_sha256: str | None
    epoch: str | None
    clock_domain: str | None
    exposure_host_stamp_s: float | None
    clock_error_bound_s: float | None
    error_bound_evidence_ref: str | None
    unknown_reasons: tuple[str, ...]
    control_ready: bool
    notes: tuple[str, ...]


def _unknown_bound():
    return ErrorBoundDict(None, None, "UNKNOWN")


def measure_review_errors(
    observed_point_camera_m,
    *,
    expected_point_camera_m,
    table_normal_camera,
    point_error_bound_m: float | None,
) -> tuple[ErrorBoundDict, ErrorBoundDict, list[str]]:
    """Planar xy + height errors for LocalizedReview (visible_top_center)."""
    unknowns: list[str] = []
    if observed_point_camera_m is None or expected_point_camera_m is None or table_normal_camera is None:
        return _unknown_bound(), _unknown_bound(), ["review_expected_or_observed_unavailable"]
    try:
        import numpy as np
        p = np.asarray(observed_point_camera_m, dtype=float)
        e = np.asarray(expected_point_camera_m, dtype=float)
        n = np.asarray(table_normal_camera, dtype=float)
        if p.shape != (3,) or e.shape != (3,) or n.shape != (3,):
            raise ValueError("bad shape")
        nn = float(np.linalg.norm(n))
        if not np.isfinite(nn) or nn <= 0:
            raise ValueError("bad normal")
        n = n / nn
        delta = p - e
        height = float(delta @ n)
        planar = float(np.linalg.norm(delta - height * n))
        bound = float(point_error_bound_m) if point_error_bound_m is not None else None
        if bound is None or not (bound > 0):
            unknowns.append("review_point_error_bound_missing")
            return (
                ErrorBoundDict(planar, None, "UNKNOWN"),
                ErrorBoundDict(height, None, "UNKNOWN"),
                unknowns,
            )
        return (
            ErrorBoundDict(planar, bound, "MEASURED"),
            ErrorBoundDict(abs(height), bound, "MEASURED"),
            unknowns,
        )
    except (TypeError, ValueError):
        return _unknown_bound(), _unknown_bound(), ["review_error_unparseable"]


def load_placement_request(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("placement request must be a JSON object")
    return payload


def select_single_valid_block(bundle):
    blocks = [b for b in bundle.get("blocks") or [] if b.get("validity") == "VALID"]
    if len(blocks) != 1:
        return None
    return blocks[0]


def classify_visibility(bundle) -> tuple[str, dict | None, list[str]]:
    """Map scene candidates to VisualSample visibility without inventing EMPTY."""
    blocks = list(bundle.get("blocks") or [])
    valid = [b for b in blocks if b.get("validity") == "VALID"]
    if len(valid) == 1:
        return "VISIBLE", valid[0], []
    if len(valid) > 1:
        return "AMBIGUOUS", None, ["multiple_valid_candidates"]
    if not blocks:
        return "EMPTY", None, []
    # Non-VALID detections / rejected candidates are not a clear empty region.
    return "AMBIGUOUS", None, ["no_single_valid_block"]


def optical_frame_for_camera(camera_id: str) -> str:
    return f"{OPTICAL_FRAME_PREFIX}{camera_id}{OPTICAL_FRAME_SUFFIX}"


def frame_id_notes(frame_id: str, camera_id: str) -> list[str]:
    expected = optical_frame_for_camera(camera_id)
    notes = []
    if frame_id == expected:
        notes.append("frame_id matches C35 color optical frame naming")
    elif frame_id in {"head", "head_optical"}:
        notes.append(
            "legacy alias frame_id=%r is NOT silently equal to %s; need explicit camera-frame bridge"
            % (frame_id, expected)
        )
    else:
        notes.append(f"frame_id={frame_id!r} differs from expected optical {expected}")
    return notes


def resolve_camera_point(
    extras: dict | None,
    point_kind: str,
) -> tuple[tuple[float, float, float] | None, list[str]]:
    """Resolve one explicit point kind. Never fall back to the other kind."""
    extras = extras or {}
    unknowns: list[str] = []
    if point_kind == POINT_KIND_MODEL_CENTER:
        raw = extras.get("model_center_camera_m")
        if raw is None:
            unknowns.append("model_center_unavailable_no_top_surface_fallback")
            return None, unknowns
    elif point_kind == POINT_KIND_VISIBLE_TOP_CENTER:
        recorded_kind = extras.get("top_surface_point_kind")
        if recorded_kind not in (None, POINT_KIND_VISIBLE_TOP_CENTER):
            unknowns.append(f"top_surface_point_kind_mismatch:{recorded_kind}")
        raw = extras.get("top_surface_point_camera_m")
        if raw is None:
            unknowns.append("visible_top_center_unavailable_no_model_center_fallback")
            return None, unknowns
        if recorded_kind is None:
            unknowns.append("top_surface_point_kind_missing")
    else:
        unknowns.append(f"unsupported_point_kind:{point_kind}")
        return None, unknowns
    try:
        center = tuple(float(x) for x in raw)
    except (TypeError, ValueError):
        unknowns.append(f"point_unparseable:{point_kind}")
        return None, unknowns
    if len(center) != 3:
        unknowns.append(f"point_wrong_dim:{point_kind}")
        return None, unknowns
    return center, unknowns


def bundle_to_visual_sample(
    bundle,
    *,
    object_id: str,
    region_id: str,
    association_confirmed: bool,
    point_kind: str = POINT_KIND_MODEL_CENTER,
    held: bool | None = None,
    released: bool | None = None,
    calibration_hash: str | None = None,
    geometry_version: str = "field_geometry_unversioned",
    scene_version: str | None = None,
) -> tuple[VisualSample | None, list[str]]:
    """Map one bundle to a VisualSample for the requested formal point kind.

    Returns (sample, unknown_reasons). Sample is None only when stamps are missing.
    """
    rgbd = bundle["rgbd"]
    timing = bundle.get("timing") or {}
    visibility, block, visibility_unknowns = classify_visibility(bundle)
    scene = timing.get("scene_consistency") or {}
    unknowns = list(visibility_unknowns)
    cal = calibration_hash if calibration_hash is not None else bundle.get("calibration_hash")
    # Sentinel lets verify() run schema checks; it is NOT a real binding hash.
    if cal:
        cal_hash = cal
        using_sentinel = False
    else:
        cal_hash = CALIBRATION_SENTINEL
        using_sentinel = True
        unknowns.append("calibration_hash_sentinel_not_binding")
    stamp = timing.get("exposure_host_stamp_s")
    if stamp is None:
        stamp = rgbd.get("host_receive_stamp")
    if stamp is None:
        return None, unknowns + ["sample_stamp_unavailable"]

    color = None
    center = None
    if block is None:
        observation_id = f"{rgbd['sample_id']}/{visibility.lower()}"
        image_ref = rgbd.get("rgb_ref") or f"{rgbd['sample_id']}#rgb"
    else:
        extras = block.get("b_extensions") or {}
        color = block.get("color")
        center, point_unknowns = resolve_camera_point(extras, point_kind)
        unknowns.extend(point_unknowns)
        observation_id = block["observation_id"]
        image_ref = rgbd.get("rgb_ref") or f"{observation_id}#rgb"
        if center is None:
            # Missing requested point must not invent VISIBLE geometry for gates.
            if visibility == "VISIBLE":
                unknowns.append(f"requested_point_missing:{point_kind}")

    sample = VisualSample(
        object_id=object_id,
        observation_id=observation_id,
        image_ref=image_ref,
        camera_id=rgbd["device_id"],
        frame_id=rgbd["frame_id"],
        stamp_s=float(stamp),
        clock_domain=timing.get("host_clock_domain") or "process_monotonic",
        epoch=rgbd["epoch"],
        source="real",
        scene_version=scene_version or rgbd["epoch"],
        config_hash=bundle.get("profile_hash") or "profile_hash_unavailable",
        calibration_hash=cal_hash,
        geometry_version=geometry_version,
        reference_confirmed=bool(association_confirmed and scene.get("scene_consistent") is True),
        region_id=region_id,
        visibility=visibility,
        color=color,
        center_camera_m=center,
        held=held,
        released=released,
    )
    if using_sentinel:
        # Keep sentinel only inside VisualSample; callers must not treat it as approved.
        pass
    return sample, unknowns


def localized_review_handoff(
    bundle,
    *,
    expected_color: str,
    target_id: str | None = None,
    slot_id: str | None = None,
    region_id: str | None = None,
    target_association_confirmed: bool = False,
    reference_id: str | None = None,
    calibration_candidate_sha256: str | None = None,
    review_point_kind: str = POINT_KIND_VISIBLE_TOP_CENTER,
    xy_m: ErrorBoundDict | None = None,
    height_m: ErrorBoundDict | None = None,
    yaw_rad: ErrorBoundDict | None = None,
    support_ok: bool | None = None,
    stable: bool | None = None,
    hand_clear: bool | None = None,
    neighbors_unchanged: bool | None = None,
) -> LocalizedReviewHandoff:
    rgbd = bundle["rgbd"]
    timing = bundle.get("timing") or {}
    scene = timing.get("scene_consistency") or {}
    visibility, block, visibility_unknowns = classify_visibility(bundle)
    unknowns: list[str] = list(visibility_unknowns)
    notes = frame_id_notes(rgbd.get("frame_id", ""), rgbd.get("device_id", ""))
    notes.append(
        f"placement_review uses {review_point_kind}; formal verify uses {POINT_KIND_MODEL_CENTER}"
    )
    if not target_association_confirmed:
        unknowns.append("target_association_unconfirmed")
    if bundle.get("calibration_hash") in (None, ""):
        unknowns.append("calibration_hash_null")
    if calibration_candidate_sha256:
        notes.append(
            "calibration_candidate_sha256 identifies candidate bytes only; not current binding"
        )
    if xy_m is None:
        xy_m = _unknown_bound()
        unknowns.append("xy_error_unknown")
    if height_m is None:
        height_m = _unknown_bound()
        unknowns.append("height_error_unknown")
    if yaw_rad is None:
        yaw_rad = _unknown_bound()
        unknowns.append("yaw_error_unknown_90deg_symmetry")
    if support_ok is None:
        unknowns.append("support_evidence_missing")
    if stable is None:
        unknowns.append("stability_evidence_missing")
    if hand_clear is None:
        unknowns.append("hand_clear_evidence_missing")
    if neighbors_unchanged is None:
        unknowns.append("neighbor_disturbance_unknown")
    if scene.get("scene_consistent") is True:
        notes.append("scene_consistent must not be copied as support/stable/hand_clear")

    color = block.get("color") if block else None
    point_kind = None
    observation_id = None
    if block is None:
        color_check = "UNKNOWN"
        if visibility == "EMPTY":
            unknowns.append("no_single_valid_block")
        elif visibility == "AMBIGUOUS":
            unknowns.append("scene_not_empty_but_no_unique_valid_block")
    else:
        extras = block.get("b_extensions") or {}
        observation_id = block.get("observation_id")
        _point, point_unknowns = resolve_camera_point(extras, review_point_kind)
        unknowns.extend(point_unknowns)
        point_kind = review_point_kind if _point is not None else extras.get("top_surface_point_kind")
        if color == expected_color:
            color_check = "MATCH"
        elif color:
            color_check = "MISMATCH"
        else:
            color_check = "UNKNOWN"
    return LocalizedReviewHandoff(
        schema_version=SCHEMA,
        target_id=target_id,
        slot_id=slot_id,
        region_id=region_id,
        scope="block",
        sample_id=rgbd["sample_id"],
        observation_id=observation_id,
        frame_id=rgbd["frame_id"],
        point_kind=point_kind,
        formal_verify_point_kind=POINT_KIND_MODEL_CENTER,
        target_association_confirmed=bool(target_association_confirmed),
        reference_id=reference_id,
        xy_m=xy_m,
        height_m=height_m,
        yaw_rad=yaw_rad,
        support_ok=support_ok,
        stable=stable,
        hand_clear=hand_clear,
        neighbors_unchanged=neighbors_unchanged,
        color=color,
        expected_color=expected_color,
        color_check=color_check,
        scene_consistent=scene.get("scene_consistent"),
        profile_hash=bundle.get("profile_hash"),
        calibration_hash=bundle.get("calibration_hash"),
        calibration_candidate_sha256=calibration_candidate_sha256,
        epoch=rgbd.get("epoch"),
        clock_domain=timing.get("host_clock_domain"),
        exposure_host_stamp_s=timing.get("exposure_host_stamp_s"),
        clock_error_bound_s=timing.get("clock_error_bound_s"),
        error_bound_evidence_ref=timing.get("error_bound_evidence_ref"),
        unknown_reasons=tuple(dict.fromkeys(unknowns)),
        control_ready=False,
        notes=tuple(notes),
    )


def handoff_to_dict(row: LocalizedReviewHandoff) -> dict:
    return asdict(row)


def load_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _request_fields(placement_request: dict | None) -> dict[str, Any]:
    req = placement_request or {}
    review = req.get("placement_review_reference") or {}
    formal = req.get("formal_verify_reference") or {}
    candidate = req.get("calibration_candidate") or {}
    post = req.get("post_place_evidence") or {}
    if review.get("point_kind") not in (None, POINT_KIND_VISIBLE_TOP_CENTER):
        raise ValueError(
            "placement_review_reference.point_kind must be visible_top_center; "
            f"got {review.get('point_kind')!r}"
        )
    if formal.get("point_kind") not in (None, POINT_KIND_MODEL_CENTER):
        raise ValueError(
            "formal_verify_reference.point_kind must be model_center; "
            f"got {formal.get('point_kind')!r}"
        )
    return {
        "target_id": req.get("target_id"),
        "slot_id": req.get("slot_id"),
        "region_id": req.get("region_id"),
        "expected_color": req.get("expected_color"),
        "association_confirmed": bool(req.get("target_association_confirmed")),
        "reference_id": req.get("reference_id"),
        "calibration_hash": req.get("calibration_hash"),
        "calibration_candidate_sha256": candidate.get("file_sha256"),
        "review_point_kind": review.get("point_kind") or POINT_KIND_VISIBLE_TOP_CENTER,
        "formal_point_kind": formal.get("point_kind") or POINT_KIND_MODEL_CENTER,
        "expected_center_camera_m": formal.get("expected_center_camera_m"),
        "table_normal_camera": formal.get("table_normal_camera") or review.get("table_normal_camera"),
        "geometry_version": formal.get("geometry_version") or "field_geometry_unversioned",
        "expected_review_point_camera_m": review.get("expected_point_camera_m"),
        "action_started_s": post.get("action_started_s"),
        "action_finished_s": post.get("action_finished_s"),
        "released": post.get("released"),
        "min_stable_s": post.get("min_stable_s"),
        "max_stable_shift_m": post.get("max_stable_shift_m"),
        "support_ok": post.get("support_ok"),
        "stable": None,  # require explicit stability window evidence, not a lone flag
        "hand_clear": post.get("hand_clear"),
        "neighbors_unchanged": post.get("neighbors_unchanged"),
        "yaw_policy": normalize_yaw_policy(req.get("yaw_policy")),
    }


def export_field_session(
    bundles_path: Path,
    *,
    expected_color: str | None = None,
    region_id: str | None = None,
    target_id: str | None = None,
    slot_id: str | None = None,
    phase: str,
    max_age_s: float = 2.656,
    association_confirmed: bool = False,
    placement_request: dict | None = None,
    placement_request_path: Path | None = None,
) -> dict:
    if placement_request is None and placement_request_path is not None:
        placement_request = load_placement_request(placement_request_path)
    fields = _request_fields(placement_request)
    # CLI / explicit args override template logical ids, but never invent association.
    expected_color = expected_color or fields["expected_color"]
    if not expected_color:
        raise ValueError("expected_color required (CLI or placement request)")
    region_id = region_id or fields["region_id"]
    if not region_id:
        raise ValueError("region_id required (CLI or placement request)")
    target_id = target_id if target_id is not None else fields["target_id"]
    slot_id = slot_id if slot_id is not None else fields["slot_id"]
    association_confirmed = bool(association_confirmed or fields["association_confirmed"])
    if association_confirmed and not target_id:
        raise ValueError("association_confirmed requires target_id")
    # Never treat observed pose as its own expected target.
    expected_center = fields["expected_center_camera_m"]
    table_normal = fields["table_normal_camera"]
    if expected_center is not None:
        expected_center = tuple(float(x) for x in expected_center)
    if table_normal is not None:
        table_normal = tuple(float(x) for x in table_normal)

    rows = load_jsonl(bundles_path)
    handoffs = []
    evidences = []
    review_expected = fields["expected_review_point_camera_m"]
    review_bound = None
    if placement_request:
        review_bound = (placement_request.get("placement_review_reference") or {}).get(
            "point_error_bound_m"
        )
    if review_expected is not None:
        review_expected = tuple(float(x) for x in review_expected)
    for bundle in rows:
        block = select_single_valid_block(bundle)
        xy_m = height_m = None
        if block is not None and review_expected is not None and table_normal is not None:
            extras = block.get("b_extensions") or {}
            obs, _ = resolve_camera_point(extras, fields["review_point_kind"])
            xy_m, height_m, _meas_unknowns = measure_review_errors(
                obs,
                expected_point_camera_m=review_expected,
                table_normal_camera=table_normal,
                point_error_bound_m=review_bound,
            )
        handoff = localized_review_handoff(
            bundle,
            expected_color=expected_color,
            target_id=target_id,
            slot_id=slot_id,
            region_id=region_id,
            target_association_confirmed=association_confirmed,
            reference_id=fields["reference_id"],
            calibration_candidate_sha256=fields["calibration_candidate_sha256"],
            review_point_kind=fields["review_point_kind"],
            xy_m=xy_m,
            height_m=height_m,
            support_ok=fields["support_ok"],
            stable=fields["stable"],
            hand_clear=fields["hand_clear"],
            neighbors_unchanged=fields["neighbors_unchanged"],
        )
        handoff_dict = handoff_to_dict(handoff)
        # Attach explicit yaw policy without forging MEASURED yaw ErrorBound values.
        if fields.get("yaw_policy"):
            handoff_dict["yaw_policy"] = fields["yaw_policy"]
            notes = list(handoff_dict.get("notes") or [])
            notes.append(
                "yaw_policy=symmetric_90_unbounded; yaw_rad stays UNKNOWN (not MEASURED)"
            )
            handoff_dict["notes"] = notes
        handoffs.append(handoff_dict)
        sample, sample_unknowns = bundle_to_visual_sample(
            bundle,
            object_id=target_id or "unassociated_candidate",
            region_id=region_id,
            association_confirmed=association_confirmed,
            point_kind=fields["formal_point_kind"],
            released=fields["released"] if phase == "post_place" else None,
            calibration_hash=fields["calibration_hash"],
            geometry_version=fields["geometry_version"],
        )
        timing = bundle.get("timing") or {}
        now_s = timing.get("output_monotonic_s")
        if sample is None or now_s is None:
            evidences.append({
                "sample_id": bundle["rgbd"]["sample_id"],
                "verdict": "UNKNOWN",
                "reason": "sample_or_output_stamp_unavailable",
                "unknown_reasons": sample_unknowns,
            })
            continue
        # Formal verify must compare model_center sample against model_center expectation.
        request = VerificationRequest(
            phase=phase,
            object_id=sample.object_id,
            region_id=region_id,
            expected_color=expected_color,
            scene_version=sample.scene_version,
            config_hash=sample.config_hash,
            calibration_hash=sample.calibration_hash,
            geometry_version=sample.geometry_version,
            clock_domain=sample.clock_domain,
            epoch=sample.epoch,
            max_age_s=max_age_s,
            source="real",
            expected_center_camera_m=expected_center,
            table_normal_camera=table_normal,
            action_started_s=fields["action_started_s"],
            action_finished_s=fields["action_finished_s"],
            min_stable_s=fields["min_stable_s"],
            max_stable_shift_m=fields["max_stable_shift_m"],
            clock_error_bound_s=timing.get("clock_error_bound_s"),
            clock_evidence_ref=timing.get("error_bound_evidence_ref"),
        )
        evidence = dict(verify(request, before=None, after=(sample,), now_s=float(now_s)))
        if sample_unknowns:
            evidence["point_semantics_unknown_reasons"] = sample_unknowns
        evidences.append(evidence)
    color_counts = {}
    for row in handoffs:
        color_counts[row["color_check"]] = color_counts.get(row["color_check"], 0) + 1
    verdict_counts = {}
    for row in evidences:
        verdict_counts[row.get("verdict", "UNKNOWN")] = (
            verdict_counts.get(row.get("verdict", "UNKNOWN"), 0) + 1
        )
    return {
        "schema_version": SCHEMA,
        "source_bundles": str(bundles_path).replace("\\", "/"),
        "phase": phase,
        "expected_color": expected_color,
        "region_id": region_id,
        "target_id": target_id,
        "slot_id": slot_id,
        "target_association_confirmed": association_confirmed,
        "placement_request_schema": (placement_request or {}).get("schema_version"),
        "placement_review_point_kind": fields["review_point_kind"],
        "formal_verify_point_kind": fields["formal_point_kind"],
        "expected_center_camera_m": expected_center,
        "table_normal_camera": table_normal,
        "calibration_hash": fields["calibration_hash"],
        "calibration_candidate_sha256": fields["calibration_candidate_sha256"],
        "n_frames": len(rows),
        "color_check_counts": color_counts,
        "verification_verdict_counts": verdict_counts,
        "control_ready": False,
        "notes": [
            "observation_id is session-local; not a persistent block_id",
            "single VALID candidate does not confirm target/slot association",
            "support/stable/hand_clear/neighbors left UNKNOWN without explicit evidence",
            "formal placement PASS requires M-provided expected pose + association + calibration_hash",
            "formal VisualSample uses model_center; LocalizedReview uses visible_top_center; no silent fallback",
            "multi-candidate / non-VALID clutter is AMBIGUOUS, not EMPTY",
            "calibration_hash_unavailable sentinel is not an approved binding",
            "never use observed pose as its own expected target",
        ],
        "localized_review_handoffs": handoffs,
        "verification_evidence": evidences,
    }
