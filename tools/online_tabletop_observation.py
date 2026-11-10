"""Camera-only producer/consumer glue for the Orbbec probe."""
import json
from pathlib import Path
from threading import Event, Thread

import numpy as np

from brick_stacking.models.camera_frame import CameraFrame
from brick_stacking.vision.clock_error_bound import load_observation_timing_bound
from brick_stacking.vision.latest_frame_pipeline import LatestFramePipeline
from brick_stacking.vision.observation_exchange import CaptureContext, profile_hash
from brick_stacking.vision.scene_consistency import SceneConsistencyMonitor
from brick_stacking.vision.tabletop_segmentation import TabletopDetector

DEFAULT_CLOCK_BOUND_EVIDENCE = (
    "docs/team/B/evidence/field_20261110/clock_error_bound_study_v0.1.json"
)


def observe(output, report, config, *, max_age_s, max_skew_s, reconnects, capture_attempt,
            clock_bound_evidence=None):
    profile = config["tabletop"]
    monitor = SceneConsistencyMonitor(**profile["temporal"]) if profile.get("temporal") else None
    pipeline = LatestFramePipeline(
        TabletopDetector(profile), nominal_edge_m=profile["nominal_edge_m"],
        max_receive_age_s=max_age_s, max_pair_skew_s=max_skew_s, monitor=monitor,
    )
    boot_path = Path("/proc/sys/kernel/random/boot_id")
    boot_epoch = boot_path.read_text(encoding="ascii").strip() if boot_path.is_file() else None
    evidence_path = Path(clock_bound_evidence or config.get("clock_error_bound_evidence")
                         or DEFAULT_CLOCK_BOUND_EVIDENCE)
    timing_bound = load_observation_timing_bound(evidence_path) if evidence_path.is_file() else None
    report["capture_attempts"] = []
    report["observation_count"] = 0
    report["limits"] = {"max_receive_age_s": max_age_s, "max_pair_skew_s": max_skew_s,
                        "status": "diagnostic_limits_not_validated"}
    report["clock_error_bound"] = (
        None if timing_bound is None else {
            "clock_error_bound_s": timing_bound[0],
            "error_bound_evidence_ref": timing_bound[1],
            "control_ready": False,
        }
    )
    event_path = output / "observation_bundles.jsonl"
    with event_path.open("w", encoding="utf-8") as events:
        for attempt in range(reconnects + 1):
            session = {"frames": [], "rejected_skew": 0, "cleanup_errors": []}
            report["capture_attempts"].append(session)
            wake, done, failed = Event(), Event(), Event()
            epoch = digest = stream = None
            prior_count = report["observation_count"]
            errors = []

            def save(frame, context):
                meta = dict(
                    camera_id=frame.camera_id, frame_id=frame.frame_id, stamp_s=frame.stamp_s,
                    clock_domain=frame.clock_domain, source=frame.source,
                    registered=frame.registered, rectified=frame.rectified, depth_unit="m",
                    host_receive_stamp_s=context.host_receive_s, host_clock_domain=context.host_clock_domain,
                    host_boot_epoch=context.host_boot_epoch, image_profile_version=context.profile,
                    profile_hash=context.profile_hash, rgb_device_stamp_s=context.color_device_s,
                    depth_device_stamp_s=context.depth_device_s,
                    depth_scale_mm=context.depth_scale_m_per_unit * 1000,
                    raw_intrinsics=context.raw_intrinsics, clock_observation=context.clock_observation,
                    clock_unavailable_reason=context.clock_unavailable_reason,
                )
                np.savez_compressed(output / context.image_ref, rgb=frame.rgb, depth_m=frame.depth_m,
                                    k=frame.k, metadata=json.dumps(meta, allow_nan=False))

            def consume():
                try:
                    while True:
                        wake.wait()
                        wake.clear()
                        bundle = pipeline.process_latest(save=save)
                        if bundle is not None:
                            events.write(json.dumps(bundle, allow_nan=False) + "\n")
                            events.flush()
                            report["observation_count"] += 1
                        if done.is_set() and not wake.is_set():
                            return
                except Exception as exc:
                    errors.append(exc)
                    failed.set()

            def offer(rgb, depth, k, meta, capture_report):
                nonlocal epoch, digest, stream
                if failed.is_set():
                    raise RuntimeError("observation worker failed") from errors[0]
                frame = CameraFrame(rgb, depth, k, **{name: meta[name] for name in (
                    "camera_id", "frame_id", "stamp_s", "clock_domain", "source",
                    "registered", "rectified",
                )})
                if epoch is None:
                    epoch = frame.clock_domain
                    stream = json.dumps(capture_report["profiles"], sort_keys=True)
                    digest = profile_hash(dict(config=config, stream=capture_report["profiles"],
                                               limits=report["limits"]))
                    pipeline.start_session(camera_id=frame.camera_id, epoch=epoch,
                                           profile=stream, profile_hash=digest)
                    session["epoch"], session["profile_hash"] = epoch, digest
                if frame.camera_id != profile["camera_id"] or list(frame.rgb.shape[:2][::-1]) != profile["image_size_wh"]:
                    raise ValueError("camera identity or resolution differs from detection profile")
                meta_row = dict(meta, host_boot_epoch=boot_epoch)
                if timing_bound is not None:
                    meta_row["clock_error_bound_s"] = timing_bound[0]
                    meta_row["error_bound_evidence_ref"] = timing_bound[1]
                context = CaptureContext.from_recording(
                    frame, meta_row,
                    image_ref=f"observed_{attempt:02d}_{frame.stamp_s:.6f}.npz", profile=stream,
                    profile_hash=digest, report=capture_report,
                )
                if pipeline.offer(frame, context):
                    wake.set()

            worker = Thread(target=consume, name="tabletop-detector")
            worker.start()
            try:
                capture_attempt(session, offer)
            except Exception as exc:
                pipeline.invalidate()
                session["result"] = "ERROR"
                session["error"] = f"{type(exc).__name__}: {exc}"
            finally:
                done.set()
                wake.set()
                worker.join()
                pipeline.invalidate()
            if errors:
                raise RuntimeError("observation worker failed") from errors[0]
            if session["cleanup_errors"]:
                raise RuntimeError("camera cleanup failed; stop before attempting another capture")
            session["observation_count"] = report["observation_count"] - prior_count
            if session["result"] != "ERROR":
                break
    report["online_metrics"] = pipeline.metrics()
    report["result"] = ("OBSERVED" if session["result"] in {"CAPTURED", "INCOMPLETE"}
                        and session["observation_count"] else "INCOMPLETE")
