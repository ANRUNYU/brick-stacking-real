"""Offline continuous replay of recorded RGB-D through LatestFramePipeline.

When NPZ metadata already carries process_monotonic host arrival, those stamps
are preserved so exposure/output stay in one domain and BundleBinding can be
constructed after an accepted clock study is injected. Otherwise host arrival is
remapped onto a synthetic process_monotonic clock for age-gate exercises only.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import time

from brick_stacking.hardware.mock_devices import RecordedCamera
from brick_stacking.vision.clock_error_bound import (
    DEFAULT_CLOCK_BOUND_EVIDENCE,
    load_observation_timing_bound,
)
from brick_stacking.vision.scene_consistency import SceneConsistencyMonitor
from brick_stacking.vision.service import VisionSession, load_tabletop_profile
from brick_stacking.vision.observation_exchange import CaptureContext


def _status_counts(bundle):
    return dict(Counter(block["b_extensions"]["candidate_status"] for block in bundle["blocks"]))


def _preserve_host_clocks(metadata):
    receive = metadata.get("host_receive_stamp_s")
    return (
        metadata.get("host_clock_domain") == "process_monotonic"
        and type(receive) in (int, float)
        and receive >= 0
    )


def replay_recordings(recordings, *, config_path, max_receive_age_s=3., max_pair_skew_s=.02,
                      inter_frame_s=1 / 15, report_path=None, clock_bound_evidence=None):
    """Feed NPZ paths in order. Returns bundles and a detection/latency summary."""
    profile, digest, name = load_tabletop_profile(config_path)
    paths = [Path(path) for path in recordings]
    if not paths:
        raise ValueError("at least one recording required")
    first_frame, first_meta = RecordedCamera.read_recording(paths[0])
    preserve = _preserve_host_clocks(first_meta)
    now = [float(first_meta["host_receive_stamp_s"]) if preserve else 1000.]
    if clock_bound_evidence is False:
        evidence_hint = None
    elif clock_bound_evidence is not None:
        evidence_hint = clock_bound_evidence
    elif preserve:
        # Field NPZ already on process_monotonic: attach accepted study when present.
        evidence_hint = DEFAULT_CLOCK_BOUND_EVIDENCE
    else:
        evidence_hint = None
    timing_bound = (
        load_observation_timing_bound(evidence_hint) if evidence_hint is not None else None
    )
    monitor = SceneConsistencyMonitor(**profile["temporal"]) if profile.get("temporal") else None
    session = VisionSession(
        config_path=config_path, max_receive_age_s=max_receive_age_s,
        max_pair_skew_s=max_pair_skew_s, monitor=monitor, clock=lambda: now[0],
    )
    epoch = f"replay/{first_meta.get('epoch', first_frame.clock_domain)}"
    session.start(camera_id=first_frame.camera_id, epoch=epoch)
    bundles = []
    rejected = []
    for path in paths:
        frame, metadata = RecordedCamera.read_recording(path)
        if frame.camera_id != first_frame.camera_id:
            raise ValueError("all recordings must share the same camera_id")
        report_file = path.with_name("camera_report.json")
        report = json.loads(report_file.read_text(encoding="utf-8")) if report_file.is_file() else None
        if preserve and not _preserve_host_clocks(metadata):
            raise ValueError("all recordings must preserve process_monotonic host arrival together")
        if preserve:
            receive = float(metadata["host_receive_stamp_s"])
            if receive < now[0]:
                raise ValueError("recorded host_receive stamps must be non-decreasing")
            now[0] = receive
            patched = dict(
                metadata,
                epoch=epoch,
                image_profile_version=name,
                profile_hash=digest,
            )
        else:
            patched = dict(
                metadata,
                host_receive_stamp_s=now[0],
                host_clock_domain="process_monotonic",
                epoch=epoch,
                image_profile_version=name,
                profile_hash=digest,
            )
        if timing_bound is not None:
            patched["clock_error_bound_s"] = timing_bound[0]
            patched["error_bound_evidence_ref"] = timing_bound[1]
        context = CaptureContext.from_recording(
            frame, patched, image_ref=path.as_posix(), profile=name,
            profile_hash=digest, report=report,
        )
        if not session.offer(frame, context):
            rejected.append({"path": path.as_posix(), "metrics": session.metrics()["counts"]})
            continue
        # Advance past host receive so process_latest can stamp output_monotonic_s.
        now[0] = max(now[0] + 1e-3, context.host_receive_s + 1e-3)
        bundle = session.process_latest()
        if bundle is None:
            rejected.append({"path": path.as_posix(), "reason": "expired_or_invalidated"})
            continue
        bundles.append({
            "path": path.as_posix(),
            "bundle": bundle,
            "status_counts": _status_counts(bundle),
            "valid_blocks": sum(1 for block in bundle["blocks"] if block["validity"] == "VALID"),
            "ambiguous_blocks": sum(
                1 for block in bundle["blocks"]
                if block["b_extensions"]["candidate_status"] == "AMBIGUOUS"
            ),
        })
        if not preserve:
            now[0] += inter_frame_s
    summary = {
        "generated_at_host": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "config_path": Path(config_path).as_posix(),
        "profile_hash": digest,
        "profile_name": name,
        "camera_id": first_frame.camera_id,
        "epoch": epoch,
        "recordings": [path.as_posix() for path in paths],
        "published": len(bundles),
        "rejected": rejected,
        "preserved_host_clocks": preserve,
        "clock_error_bound_s": None if timing_bound is None else timing_bound[0],
        "error_bound_evidence_ref": None if timing_bound is None else timing_bound[1],
        "per_frame": [
            {
                "path": row["path"],
                "status_counts": row["status_counts"],
                "valid_blocks": row["valid_blocks"],
                "ambiguous_blocks": row["ambiguous_blocks"],
                "control_ready": row["bundle"]["control_ready"],
                "timing_validity": row["bundle"]["timing"]["validity"],
                "clock_error_bound_s": row["bundle"]["timing"]["clock_error_bound_s"],
                "error_bound_evidence_ref": row["bundle"]["timing"]["error_bound_evidence_ref"],
                "output_monotonic_s": row["bundle"]["timing"].get("output_monotonic_s"),
                "exposure_to_output_s": row["bundle"]["timing"]["exposure_to_output_s"],
                "receive_to_output_s": row["bundle"]["timing"]["receive_to_output_s"],
            }
            for row in bundles
        ],
        "online_metrics": session.metrics(),
        "limits": {
            "max_receive_age_s": max_receive_age_s,
            "max_pair_skew_s": max_pair_skew_s,
            "status": "diagnostic_replay_limits_not_field_validated",
        },
        "independent_scene_validation": False,
        "control_ready": False,
        "notes": [
            ("Preserved recorded process_monotonic host arrival for binding-capable timing."
             if preserve else
             "Host arrival remapped to synthetic process_monotonic for age-gate replay."),
            ("Accepted clock study injected into CaptureContext."
             if timing_bound is not None else
             "No accepted clock study injected; timing.validity stays UNKNOWN without bound."),
            "Same-scene development recordings are not an independent validation set.",
        ],
    }
    if report_path is not None:
        out = Path(report_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return bundles, summary
