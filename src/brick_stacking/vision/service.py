"""CONTRACTS-facing V API: get_observation / detect_blocks / verify / replay.

Does not elevate control_ready. Clock error bounds stay UNKNOWN until field-validated.
"""
from __future__ import annotations

from pathlib import Path

from brick_stacking.contracts import ObservationBundle, VerificationEvidence
from brick_stacking.hardware.mock_devices import RecordedCamera
from brick_stacking.runtime.config_loader import load_config
from brick_stacking.verification.visual_transition import (
    VerificationRequest,
    VisualSample,
    verify as verify_evidence,
)
from brick_stacking.vision.latest_frame_pipeline import LatestFramePipeline
from brick_stacking.vision.observation_exchange import (
    CaptureContext,
    observation_exchange,
    profile_hash,
)
from brick_stacking.vision.tabletop_segmentation import TabletopDetector


def load_tabletop_profile(config_path):
    config = load_config(config_path)
    profile = config["tabletop"]
    return profile, profile_hash(profile), Path(config_path).stem


def detect_blocks(frame, profile):
    """Run tabletop detection on one CameraFrame. Returns TabletopObservation."""
    return TabletopDetector(profile).detect(frame)


def replay(recording, *, config_path, recorded=True, stale=False,
           report_path=None, image_ref=None, clock_bound_evidence=None) -> ObservationBundle:
    """Rebuild one ObservationBundle from an NPZ recording.

    Optional accepted clock study fills timing bound/evidence. Single-frame replay
    still omits output_monotonic_s; use replay_recordings for binding-capable stamps.
    """
    path = Path(recording)
    frame, metadata = RecordedCamera.read_recording(path)
    profile, digest, name = load_tabletop_profile(config_path)
    report_file = Path(report_path) if report_path else path.with_name("camera_report.json")
    report = None
    if report_file.is_file():
        import json
        report = json.loads(report_file.read_text(encoding="utf-8"))
    patched = dict(metadata)
    if clock_bound_evidence is not None:
        from brick_stacking.vision.clock_error_bound import load_observation_timing_bound
        timing_bound = load_observation_timing_bound(clock_bound_evidence)
        if timing_bound is not None:
            patched["clock_error_bound_s"] = timing_bound[0]
            patched["error_bound_evidence_ref"] = timing_bound[1]
    context = CaptureContext.from_recording(
        frame, patched,
        image_ref=image_ref or path.as_posix(),
        profile=name, profile_hash=digest, report=report,
    )
    return observation_exchange(
        frame, context, detect_blocks(frame, profile),
        nominal_edge_m=profile["nominal_edge_m"], recorded=recorded, stale=stale,
    )


def verify(request: VerificationRequest, *, before: VisualSample | None,
           after: tuple[VisualSample, ...], now_s: float) -> VerificationEvidence:
    """Pass-through to scoped visual evidence. Missing images → UNKNOWN, never fake PASS."""
    return verify_evidence(request, before=before, after=after, now_s=now_s)


class VisionSession:
    """Bound latest-pair producer/consumer for one camera session."""

    def __init__(self, *, config_path, max_receive_age_s, max_pair_skew_s, monitor=None,
                 clock=None):
        profile, digest, name = load_tabletop_profile(config_path)
        kwargs = dict(
            detector=TabletopDetector(profile),
            nominal_edge_m=profile["nominal_edge_m"],
            max_receive_age_s=max_receive_age_s,
            max_pair_skew_s=max_pair_skew_s,
            monitor=monitor,
        )
        if clock is not None:
            kwargs["clock"] = clock
        self.profile = profile
        self.profile_name = name
        self.profile_hash = digest
        self.pipeline = LatestFramePipeline(**kwargs)

    def start(self, *, camera_id, epoch):
        self.pipeline.start_session(
            camera_id=camera_id, epoch=epoch,
            profile=self.profile_name, profile_hash=self.profile_hash,
        )

    def offer(self, frame, context: CaptureContext):
        return self.pipeline.offer(frame, context)

    def process_latest(self, *, save=None):
        return self.pipeline.process_latest(save=save)

    def get_observation(self) -> ObservationBundle | None:
        return self.pipeline.get_observation()

    def metrics(self):
        return self.pipeline.metrics()

    def invalidate(self):
        self.pipeline.invalidate()
