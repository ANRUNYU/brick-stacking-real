"""Build verify / placement-review handoff records from ObservationBundle rows.

Does not invent target association, support/stable/hand-clear evidence, yaw, or
calibration hashes. Does not raise control_ready.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path

from brick_stacking.verification.visual_transition import (
    VerificationRequest,
    VisualSample,
    verify,
)

SCHEMA = "v-verify-field-handoff-0.1"
OPTICAL_FRAME_PREFIX = "camera_"
OPTICAL_FRAME_SUFFIX = "_color_optical_frame"


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
    region_id: str | None
    scope: str
    sample_id: str
    observation_id: str | None
    frame_id: str
    point_kind: str | None
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


def select_single_valid_block(bundle):
    blocks = [b for b in bundle.get("blocks") or [] if b.get("validity") == "VALID"]
    if len(blocks) != 1:
        return None
    return blocks[0]


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


def bundle_to_visual_sample(
    bundle,
    *,
    object_id: str,
    region_id: str,
    association_confirmed: bool,
    held: bool | None = None,
    released: bool | None = None,
    calibration_hash: str | None = None,
    geometry_version: str = "field_geometry_unversioned",
    scene_version: str | None = None,
) -> VisualSample | None:
    """Map one bundle to a VisualSample when a single VALID block exists or EMPTY scene."""
    rgbd = bundle["rgbd"]
    timing = bundle.get("timing") or {}
    block = select_single_valid_block(bundle)
    scene = timing.get("scene_consistency") or {}
    cal = calibration_hash if calibration_hash is not None else bundle.get("calibration_hash")
    # Real field bundles currently ship calibration_hash=null; keep explicit sentinel for verify.
    cal_hash = cal if cal else "calibration_hash_unavailable"
    stamp = timing.get("exposure_host_stamp_s")
    if stamp is None:
        stamp = rgbd.get("host_receive_stamp")
    if stamp is None:
        return None
    if block is None:
        visibility = "EMPTY"
        color = None
        center = None
        observation_id = f"{rgbd['sample_id']}/empty"
        image_ref = rgbd.get("rgb_ref") or f"{rgbd['sample_id']}#rgb"
    else:
        extras = block.get("b_extensions") or {}
        visibility = "VISIBLE"
        color = block.get("color")
        center = extras.get("model_center_camera_m") or extras.get("top_surface_point_camera_m")
        if center is not None:
            center = tuple(float(x) for x in center)
        observation_id = block["observation_id"]
        image_ref = rgbd.get("rgb_ref") or f"{observation_id}#rgb"
    return VisualSample(
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


def localized_review_handoff(
    bundle,
    *,
    expected_color: str,
    target_id: str | None = None,
    region_id: str | None = None,
    target_association_confirmed: bool = False,
    reference_id: str | None = None,
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
    block = select_single_valid_block(bundle)
    unknowns: list[str] = []
    notes = frame_id_notes(rgbd.get("frame_id", ""), rgbd.get("device_id", ""))
    if not target_association_confirmed:
        unknowns.append("target_association_unconfirmed")
    if bundle.get("calibration_hash") in (None, ""):
        unknowns.append("calibration_hash_null")
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
    if block is None:
        color_check = "UNKNOWN"
        unknowns.append("no_single_valid_block")
        point_kind = None
        observation_id = None
    else:
        extras = block.get("b_extensions") or {}
        point_kind = extras.get("top_surface_point_kind")
        observation_id = block.get("observation_id")
        if color == expected_color:
            color_check = "MATCH"
        elif color:
            color_check = "MISMATCH"
        else:
            color_check = "UNKNOWN"
        if point_kind != "visible_top_center":
            unknowns.append("point_kind_not_visible_top_center")
    return LocalizedReviewHandoff(
        schema_version=SCHEMA,
        target_id=target_id,
        region_id=region_id,
        scope="block",
        sample_id=rgbd["sample_id"],
        observation_id=observation_id,
        frame_id=rgbd["frame_id"],
        point_kind=point_kind,
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
        epoch=rgbd.get("epoch"),
        clock_domain=timing.get("host_clock_domain"),
        exposure_host_stamp_s=timing.get("exposure_host_stamp_s"),
        clock_error_bound_s=timing.get("clock_error_bound_s"),
        error_bound_evidence_ref=timing.get("error_bound_evidence_ref"),
        unknown_reasons=tuple(unknowns),
        control_ready=False,
        notes=tuple(notes),
    )


def handoff_to_dict(row: LocalizedReviewHandoff) -> dict:
    payload = asdict(row)
    return payload


def load_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def export_field_session(
    bundles_path: Path,
    *,
    expected_color: str,
    region_id: str,
    target_id: str | None,
    phase: str,
    max_age_s: float = 2.656,
    association_confirmed: bool = False,
) -> dict:
    rows = load_jsonl(bundles_path)
    handoffs = []
    evidences = []
    for bundle in rows:
        handoff = localized_review_handoff(
            bundle,
            expected_color=expected_color,
            target_id=target_id,
            region_id=region_id,
            target_association_confirmed=association_confirmed,
        )
        handoffs.append(handoff_to_dict(handoff))
        sample = bundle_to_visual_sample(
            bundle,
            object_id=target_id or "unassociated_candidate",
            region_id=region_id,
            association_confirmed=association_confirmed,
        )
        timing = bundle.get("timing") or {}
        now_s = timing.get("output_monotonic_s")
        if sample is None or now_s is None:
            evidences.append({
                "sample_id": bundle["rgbd"]["sample_id"],
                "verdict": "UNKNOWN",
                "reason": "sample_or_output_stamp_unavailable",
            })
            continue
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
            expected_center_camera_m=None,
            table_normal_camera=None,
            clock_error_bound_s=timing.get("clock_error_bound_s"),
            clock_evidence_ref=timing.get("error_bound_evidence_ref"),
        )
        evidence = verify(request, before=None, after=(sample,), now_s=float(now_s))
        evidences.append(dict(evidence))
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
        "target_association_confirmed": association_confirmed,
        "n_frames": len(rows),
        "color_check_counts": color_counts,
        "verification_verdict_counts": verdict_counts,
        "control_ready": False,
        "notes": [
            "observation_id is session-local; not a persistent block_id",
            "single VALID candidate does not confirm target/slot association",
            "support/stable/hand_clear/neighbors left UNKNOWN without explicit evidence",
            "formal placement PASS requires M-provided expected pose + association + calibration_hash",
        ],
        "localized_review_handoffs": handoffs,
        "verification_evidence": evidences,
    }
