"""Map existing RGB-D frames and detections to the draft V/M contract."""
from dataclasses import dataclass
from hashlib import sha256
import math

import numpy as np
import yaml

from brick_stacking.contracts import ObservationBundle, SCHEMA_VERSION
from brick_stacking.models.block_detection import BlockDetection, SegmentationStatus
from brick_stacking.vision.tabletop_segmentation import TabletopObservation


def profile_hash(profile):
    return sha256(yaml.safe_dump(profile, sort_keys=True).encode("utf-8")).hexdigest()


def _stamp(value):
    if value is None:
        return None
    if type(value) not in (float, int) or not math.isfinite(value) or value < 0:
        raise ValueError("invalid camera timestamp or depth scale")
    return float(value)


EXPOSURE_REFERENCE_GLOBAL_MONOTONIC = (
    "orbbec_color_global_timestamp_mapped_to_process_monotonic"
)


def exposure_host_candidate_s(clock_observation):
    """Return SDK global→host-monotonic exposure candidate, or None."""
    if not clock_observation:
        return None
    color = clock_observation.get("frames", {}).get("color") or {}
    value = color.get("global_host_monotonic_candidate_s")
    if not color.get("global_available") or value is None:
        return None
    return float(value)


@dataclass(frozen=True)
class CaptureContext:
    """Acquisition metadata for one immutable CameraFrame, in seconds/metres."""
    image_ref: str
    profile: str
    profile_hash: str
    epoch: str
    host_receive_s: float | None = None
    host_clock_domain: str | None = None
    color_device_s: float | None = None
    depth_device_s: float | None = None
    depth_scale_m_per_unit: float | None = None
    clock_observation: dict | None = None
    raw_intrinsics: dict | None = None
    host_boot_epoch: str | None = None
    clock_unavailable_reason: str | None = None
    capture_profile_hash: str | None = None
    clock_error_bound_s: float | None = None
    error_bound_evidence_ref: str | None = None

    def __post_init__(self):
        if not all((self.image_ref, self.profile, self.profile_hash, self.epoch)):
            raise ValueError("image reference, profile hash and session epoch required")
        for value in (self.host_receive_s, self.color_device_s, self.depth_device_s,
                      self.depth_scale_m_per_unit, self.clock_error_bound_s):
            _stamp(value)
        if (self.host_receive_s is None) != (self.host_clock_domain is None):
            raise ValueError("host arrival must name its clock domain")
        if self.depth_scale_m_per_unit == 0:
            raise ValueError("depth scale must be positive")
        if (self.clock_error_bound_s is None) != (self.error_bound_evidence_ref is None):
            raise ValueError("clock error bound and evidence ref must be set together")
        if self.clock_error_bound_s is not None and not self.error_bound_evidence_ref:
            raise ValueError("clock error bound requires evidence ref")
        if self.clock_error_bound_s == 0:
            raise ValueError("zero clock error bound is not allowed")

    @property
    def rgb_depth_delta_s(self):
        if self.color_device_s is None or self.depth_device_s is None:
            return None
        return abs(self.color_device_s - self.depth_device_s)

    @classmethod
    def from_recording(cls, frame, metadata, *, image_ref, profile, profile_hash, report=None):
        report = report or {}
        row = next((row for row in report.get("frames", ())
                    if row["file"] == image_ref.replace("\\", "/").rsplit("/", 1)[-1]), {})
        clocks = metadata.get("clock_observation") or row.get("clock_observation")
        if clocks and clocks.get("schema_version") != "c-orbbec-clock-observation-1":
            raise ValueError("unsupported SDK clock observation schema")
        readings = clocks["frames"] if clocks else {}
        color = metadata.get("rgb_device_stamp_s", row.get("rgb_stamp_s"))
        depth = metadata.get("depth_device_stamp_s", row.get("depth_stamp_s"))
        if clocks:
            color = readings["color"]["device_timestamp_us"] / 1e6 if color is None else color
            depth = readings["depth"]["device_timestamp_us"] / 1e6 if depth is None else depth
        if color is None and frame.clock_domain.startswith("orbbec_"):
            color = frame.stamp_s
        if color is not None and not math.isclose(color, frame.stamp_s, abs_tol=1e-6, rel_tol=0):
            raise ValueError("recorded color stamp does not match the RGB-D frame")
        scale = metadata.get("depth_scale_mm", row.get("depth_scale_mm"))
        bound = metadata.get("clock_error_bound_s", report.get("clock_error_bound_s"))
        evidence = metadata.get("error_bound_evidence_ref", report.get("error_bound_evidence_ref"))
        return cls(
            image_ref=image_ref,
            profile=metadata.get("image_profile_version", profile),
            profile_hash=profile_hash,
            epoch=metadata.get("epoch", frame.clock_domain),
            host_receive_s=metadata.get("host_receive_stamp_s", row.get("host_receive_stamp_s")),
            host_clock_domain=metadata.get("host_clock_domain", row.get("host_clock_domain")),
            color_device_s=color,
            depth_device_s=depth,
            depth_scale_m_per_unit=scale / 1000 if scale is not None else None,
            clock_observation=clocks,
            raw_intrinsics=metadata.get("raw_intrinsics", report.get("calibration")),
            host_boot_epoch=metadata.get("host_boot_epoch", report.get("host_boot_epoch")),
            clock_unavailable_reason=metadata.get("clock_unavailable_reason",
                                                  report.get("sdk_clock_unavailable_reason")),
            capture_profile_hash=metadata.get("profile_hash"),
            clock_error_bound_s=None if bound is None else float(bound),
            error_bound_evidence_ref=evidence,
        )


def observation_exchange(frame, context, detections, *, nominal_edge_m, recorded=False,
                         stale=False, unavailable_reason=None) -> ObservationBundle:
    """Export position-only candidates without inventing pose or timing evidence."""
    sample_id = f"{frame.camera_id}/{context.epoch}/{frame.stamp_s!r}"
    source = "recorded" if recorded else {"synthetic": "mock", "real_measured": "real"}.get(
        frame.source, frame.source
    )
    if source not in {"mock", "recorded", "real"}:
        raise ValueError("unrecognized camera source")
    valid_depth_ratio = float(np.mean(np.isfinite(frame.depth_m) & (frame.depth_m > 0)))
    reason = "stale_observation" if stale else unavailable_reason
    if valid_depth_ratio == 0 and reason is None:
        reason = "invalid_depth"
    sample = dict(
        sample_id=sample_id, source=source, device_id=frame.camera_id, frame_id=frame.frame_id,
        device_stamp=context.color_device_s, host_receive_stamp=context.host_receive_s,
        clock_domain=frame.clock_domain, epoch=context.epoch,
        validity="INVALID" if stale or valid_depth_ratio == 0 else "UNKNOWN" if reason else "VALID",
        reason=reason,
    )
    rgbd = dict(
        sample, camera_sn=frame.camera_id, rgb_ref=f"{context.image_ref}#rgb",
        depth_ref=f"{context.image_ref}#depth_m", intrinsics_k=tuple(frame.k.flat),
        distortion_d=(), depth_scale_m_per_unit=context.depth_scale_m_per_unit,
        profile=context.profile, depth_registered_to_rgb=frame.registered,
        rgb_depth_delta_s=context.rgb_depth_delta_s,
    )
    exposure_host = exposure_host_candidate_s(context.clock_observation)
    bound = context.clock_error_bound_s
    evidence_ref = context.error_bound_evidence_ref
    if bound is not None and (bound < 0 or evidence_ref is None):
        raise ValueError("clock error bound requires non-negative value and evidence ref")
    if bound is None or exposure_host is None:
        timing_validity, timing_reason = "UNKNOWN", (
            "clock_mapping_bound_unvalidated" if exposure_host is not None
            else "exposure_reference_and_clock_mapping_unvalidated"
        )
        bound, evidence_ref = None, None
    else:
        # Bound authorizes timing fields only; ObservationBundle.control_ready stays false.
        timing_validity, timing_reason = "VALID", None
    timing = dict(
        frame_stamp_s=frame.stamp_s, device_clock_domain=frame.clock_domain,
        color_device_stamp_s=context.color_device_s, depth_device_stamp_s=context.depth_device_s,
        host_receive_stamp_s=context.host_receive_s, host_clock_domain=context.host_clock_domain,
        host_boot_epoch=context.host_boot_epoch, sdk_clock_observation=context.clock_observation,
        rgb_depth_delta_s=context.rgb_depth_delta_s,
        exposure_reference=(EXPOSURE_REFERENCE_GLOBAL_MONOTONIC if exposure_host is not None else None),
        exposure_host_stamp_s=exposure_host, clock_error_bound_s=bound,
        error_bound_evidence_ref=evidence_ref,
        validity=timing_validity, reason=timing_reason,
        sdk_clock_unavailable_reason=context.clock_unavailable_reason,
        capture_profile_hash=context.capture_profile_hash,
        original_source=frame.source, valid_depth_ratio=valid_depth_ratio,
        raw_intrinsics=context.raw_intrinsics,
    )
    candidates = detections.candidates if isinstance(detections, TabletopObservation) else detections
    blocks = []
    for index, candidate in enumerate(candidates):
        if isinstance(candidate, BlockDetection):
            status, candidate_reason = candidate.status.value, candidate.reason
            top, center, span = candidate.surface_point_camera_m, None, candidate.estimated_span_m
            color = candidate.color
            if candidate.camera_id != frame.camera_id:
                raise ValueError("candidate camera differs from RGB-D frame")
            stamp = candidate.stamp_s, candidate.clock_domain, candidate.frame_id
        else:
            status, candidate_reason = candidate["status"], candidate["reason"]
            top, center = candidate.get("top_surface_center_camera_m"), candidate.get("center_camera_m")
            span, color = candidate.get("footprint_size_m"), candidate["color"]
            stamp = candidate["stamp_s"], candidate["clock_domain"], candidate["frame_id"]
        if stamp != (frame.stamp_s, frame.clock_domain, frame.frame_id):
            raise ValueError("candidate does not belong to this RGB-D frame")
        single = status in {"SINGLE_CUBE_CANDIDATE", SegmentationStatus.UNAMBIGUOUS.value}
        candidate_validity = "UNKNOWN" if not single else "VALID"
        if status == SegmentationStatus.INVALID_DEPTH.value:
            candidate_validity = "INVALID"
        validity = sample["validity"] if reason else candidate_validity
        blocks.append(dict(
            sample, observation_id=f"{sample_id}/{index}", color=color,
            validity=validity, reason=reason or candidate_reason, camera_pose=None,
            size_m=(nominal_edge_m,) * 3 if single else None,
            size_source="nominal_profile" if single else "unknown",
            quality=None, covariance=None, visibility="VISIBLE_CANDIDATE",
            b_extensions=dict(
                candidate_status=status, top_surface_point_camera_m=top if single else None,
                top_surface_point_kind=("surface_sample" if isinstance(candidate, BlockDetection)
                                        else "visible_top_center") if top is not None and single else None,
                model_center_camera_m=center if single else None,
                center_source="top_center_minus_half_nominal_edge_along_plane_normal" if center is not None and single else None,
                measured_top_span_m=span, orientation=None,
                yaw_symmetry_period_rad=math.pi / 2 if single else None,
            ),
        ))
    return dict(schema_version=SCHEMA_VERSION, rgbd=rgbd, blocks=blocks, timing=timing,
                profile_hash=context.profile_hash, control_ready=False, calibration_hash=None)
