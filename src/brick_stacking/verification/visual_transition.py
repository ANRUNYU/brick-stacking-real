"""Review explicitly associated visual evidence without issuing task commands."""
from dataclasses import dataclass
import math
from uuid import uuid4

import numpy as np

from brick_stacking.contracts import SCHEMA_VERSION, Source, VerificationEvidence


@dataclass(frozen=True)
class VisualSample:
    object_id: str
    observation_id: str
    image_ref: str
    camera_id: str
    frame_id: str
    stamp_s: float
    clock_domain: str
    epoch: str
    source: Source
    scene_version: str
    config_hash: str
    calibration_hash: str
    geometry_version: str
    reference_confirmed: bool
    region_id: str
    visibility: str  # VISIBLE, EMPTY, OCCLUDED, INVALID_DEPTH or AMBIGUOUS
    color: str | None = None
    center_camera_m: tuple[float, float, float] | None = None
    held: bool | None = None
    released: bool | None = None


@dataclass(frozen=True)
class VerificationRequest:
    phase: str
    object_id: str
    region_id: str
    expected_color: str
    scene_version: str
    config_hash: str
    calibration_hash: str
    geometry_version: str
    clock_domain: str
    epoch: str
    max_age_s: float
    source: Source
    expected_center_camera_m: tuple[float, float, float] | None = None
    table_normal_camera: tuple[float, float, float] | None = None
    action_started_s: float | None = None
    action_finished_s: float | None = None
    min_stable_s: float | None = None
    max_stable_shift_m: float | None = None
    clock_error_bound_s: float | None = None
    clock_evidence_ref: str | None = None


def _point(value):
    if value is None:
        return None
    point = np.asarray(value, dtype=float)
    return point if point.shape == (3,) and np.isfinite(point).all() else None


def verify(request: VerificationRequest, *, before: VisualSample | None,
           after: tuple[VisualSample, ...], now_s: float) -> VerificationEvidence:
    """Produce evidence for one target/region. Post-action samples are in capture order."""
    phase = {"PICK": "post_grasp", "PLACE": "post_place"}.get(request.phase, request.phase)
    if phase not in {"pre_grasp", "post_grasp", "post_place"}:
        raise ValueError("unknown verification phase")
    primary = after[-1] if after else None
    samples = ((before,) if before else ()) + after

    def evidence(verdict, reason, *, error=None, scope=None):
        refs = tuple(view.observation_id for view in (before, primary) if view is not None)
        result = VerificationEvidence(
            schema_version=SCHEMA_VERSION, sample_id=uuid4().hex,
            source=request.source,
            device_id=primary.camera_id if primary else "unavailable",
            frame_id=primary.frame_id if primary else "unavailable",
            device_stamp=None, host_receive_stamp=primary.stamp_s if primary else None,
            clock_domain=request.clock_domain, epoch=request.epoch,
            validity="UNKNOWN" if verdict == "UNKNOWN" else "VALID", reason=reason,
            object_id=request.object_id, phase=request.phase, verdict=verdict, error_m=error,
            image_refs=tuple(view.image_ref for view in samples if view.image_ref),
            observation_refs=refs, region_id=request.region_id, scene_version=request.scene_version,
            config_hash=request.config_hash, calibration_hash=request.calibration_hash,
            supporting_observation_refs=tuple(view.observation_id for view in after[:-1]),
        )
        if scope is not None:
            result["scope"] = scope
        return result

    if primary is None or (phase != "pre_grasp" and before is None):
        return evidence("UNKNOWN", "missing_images")
    required = (request.object_id, request.region_id, request.expected_color, request.scene_version,
                request.config_hash, request.calibration_hash, request.geometry_version,
                request.clock_domain, request.epoch)
    if not all(required) or not math.isfinite(request.max_age_s) or request.max_age_s <= 0:
        return evidence("UNKNOWN", "verification_context_unavailable")
    bound = 0.
    if request.source == "real":
        bound = request.clock_error_bound_s
        if bound is None or not math.isfinite(bound) or bound < 0 or not request.clock_evidence_ref:
            return evidence("UNKNOWN", "real_exposure_clock_unvalidated")
    if (len({view.observation_id for view in samples}) != len(samples)
            or len({view.image_ref for view in samples}) != len(samples)
            or any(not view.observation_id or not view.image_ref for view in samples)):
        return evidence("UNKNOWN", "missing_or_reused_frame")
    for view in samples:
        if (view.clock_domain, view.epoch, view.scene_version, view.config_hash,
                view.calibration_hash, view.geometry_version) != (
                request.clock_domain, request.epoch, request.scene_version, request.config_hash,
                request.calibration_hash, request.geometry_version):
            return evidence("UNKNOWN", "scene_clock_or_geometry_version_changed")
        if (view.camera_id, view.frame_id, view.source) != (
                primary.camera_id, primary.frame_id, request.source):
            return evidence("UNKNOWN", "camera_reference_changed")
        if view.object_id != request.object_id:
            return evidence("UNKNOWN", "target_association_changed")
        if view.reference_confirmed is not True:
            return evidence("UNKNOWN", "camera_or_table_reference_unconfirmed")
    stamps = [view.stamp_s for view in samples]
    if (not all(math.isfinite(stamp) and stamp >= 0 for stamp in stamps)
            or any(a >= b for a, b in zip(stamps, stamps[1:]))):
        return evidence("UNKNOWN", "reversed_or_reused_timestamp")
    if any(not bound <= now_s - view.stamp_s <= request.max_age_s - bound for view in after):
        return evidence("UNKNOWN", "stale_or_future_frame")
    if before is not None:
        if before.visibility not in {"VISIBLE", "EMPTY"}:
            return evidence("UNKNOWN", "before_action_reference_unobservable")
        started = now_s if phase == "pre_grasp" else request.action_started_s
        if started is None or not bound <= started - before.stamp_s <= request.max_age_s - bound:
            return evidence("UNKNOWN", "stale_or_missing_before_action_reference")
    if phase != "pre_grasp":
        finished = request.action_finished_s
        if finished is None or not started <= finished < after[0].stamp_s - bound:
            return evidence("UNKNOWN", "frames_do_not_follow_completed_action")
    if any(view.region_id != request.region_id for view in after):
        return evidence("UNKNOWN", "wrong_verification_region")
    for view in after:
        if view.visibility not in {"VISIBLE", "EMPTY"}:
            return evidence("UNKNOWN", {"OCCLUDED": "target_occluded",
                                        "INVALID_DEPTH": "invalid_depth",
                                        "AMBIGUOUS": "ambiguous_target"}.get(
                                            view.visibility, "region_unobservable"))

    if phase == "post_grasp":
        if primary.held is False and primary.visibility == "EMPTY":
            return evidence("FAIL", "observed_empty_gripper", scope="held")
        if primary.visibility != "VISIBLE" or primary.held is not True:
            return evidence("UNKNOWN", "positive_hold_evidence_missing")
        if not primary.color:
            return evidence("UNKNOWN", "target_color_unknown")
        if primary.color != request.expected_color:
            return evidence("FAIL", "held_target_color_mismatch", scope="held")
        return evidence("PASS", "associated_target_observed_held", scope="held")

    if primary.visibility == "EMPTY":
        return evidence("FAIL", "target_region_empty", scope="position_only")
    expected, normal = _point(request.expected_center_camera_m), _point(request.table_normal_camera)
    if expected is None or normal is None or not math.isclose(np.linalg.norm(normal), 1, abs_tol=1e-6):
        return evidence("UNKNOWN", "expected_camera_position_or_plane_unavailable")
    limit = 0.010 if phase == "pre_grasp" else 0.015
    positions, errors = [], []
    for view in after:
        point = _point(view.center_camera_m)
        if view.visibility != "VISIBLE" or not view.color or point is None:
            return evidence("UNKNOWN", "target_color_or_position_unobserved")
        delta = point - expected
        height = float(delta @ normal)
        error = float(np.linalg.norm(delta - height * normal))
        if view.color != request.expected_color:
            return evidence("FAIL", "target_color_mismatch", error=error, scope="position_only")
        if error > limit or (phase == "pre_grasp" and abs(height) > 0.008):
            return evidence("FAIL", "target_outside_position_gate", error=error, scope="position_only")
        positions.append(point)
        errors.append(error)
    error = max(errors)
    if phase == "pre_grasp":
        return evidence("PASS", "visible_target_within_position_gate", error=error, scope="position_only")
    if any(view.released is not True for view in after):
        return evidence("UNKNOWN", "positive_release_evidence_missing", error=error)
    duration, drift = request.min_stable_s, request.max_stable_shift_m
    if (duration is None or not math.isfinite(duration) or duration <= 0 or drift is None
            or not math.isfinite(drift) or not 0 < drift <= limit or len(after) < 2
            or primary.stamp_s - after[0].stamp_s - 2 * bound < duration):
        return evidence("UNKNOWN", "stability_window_unavailable", error=error)
    if any(np.linalg.norm(point - previous) > drift for index, point in enumerate(positions)
           for previous in positions[:index]):
        return evidence("FAIL", "target_moved_after_release", error=error, scope="released_stable")
    return evidence("PASS", "released_target_stable_within_slot_gate", error=error, scope="released_stable")
