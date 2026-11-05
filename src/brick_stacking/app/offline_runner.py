"""Replay explicit RGB-D recordings or a labelled synthetic smoke fixture."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import numpy as np
from brick_stacking.hardware.mock_devices import RecordedCamera
from brick_stacking.models.camera_frame import CameraFrame
from brick_stacking.runtime.config_loader import load_config
from brick_stacking.runtime.run_recorder import RunRecorder
from brick_stacking.vision.block_instance_segmentation import BlockDetector


def synthetic_frame():
    """Four isolated frontoparallel faces + one inseparable red two-cube face.

    Pixel geometry is fixture-only, not a real-camera profile or calibration.
    """
    rgb = np.full((160, 240, 3), 100, np.uint8)
    depth = np.ones((160, 240), float)
    for color, x in (((255, 0, 0), 10), ((255, 255, 0), 65),
                     ((0, 255, 0), 120), ((0, 0, 255), 175)):
        rgb[20:40, x:x + 20] = color
        depth[20:40, x:x + 20] = 0.5
    rgb[90:110, 20:60] = (255, 0, 0)
    depth[90:110, 20:60] = 0.5
    return CameraFrame(rgb, depth, np.array([[200, 0, 120], [0, 200, 80], [0, 0, 1]]),
        "synthetic_head", "synthetic_camera_optical_frame", 1.0, "synthetic_epoch_1",
        "synthetic", True, True)


def save_recording(path, frame):
    meta = {name: getattr(frame, name) for name in ("camera_id", "frame_id", "stamp_s",
            "clock_domain", "source", "registered", "rectified")}
    meta["depth_unit"] = "m"
    np.savez_compressed(path, rgb=frame.rgb, depth_m=frame.depth_m, k=frame.k,
                        metadata=json.dumps(meta))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="config/defaults.yaml")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--synthetic", action="store_true")
    g.add_argument("--recordings", nargs="+", help="NPZ paths; see docs/DATA_FORMAT.md")
    p.add_argument("--output-root", default="artifacts/test_runs")
    args = p.parse_args(argv)
    config = load_config(args.config)
    detector = BlockDetector(config["vision"])
    recorder = RunRecorder(args.output_root, "Perception", "AdjacentBlocks", "RGBD", config)
    try:
        frames = [synthetic_frame()] if args.synthetic else [
            RecordedCamera([path]).get_synced_rgbd() for path in args.recordings]
        observations = []
        for index, frame in enumerate(frames):
            detections = detector.detect(frame)
            data = {"frame_index": index, "source": frame.source,
                    "detections": [asdict(d) for d in detections]}
            observations.append(data)
            recorder.event("observation", data)
        if args.synthetic:
            save_recording(recorder.path / "synthetic_rgbd.npz", frames[0])
        flat = [d for o in observations for d in o["detections"]]
        counts = {s: sum(d["status"] == s for d in flat) for s in
                  ("UNAMBIGUOUS", "AMBIGUOUS", "INVALID_DEPTH")}
        expected = counts == {"UNAMBIGUOUS": 4, "AMBIGUOUS": 1, "INVALID_DEPTH": 0}
        result = ("PASS" if expected else "FAIL") if args.synthetic else "INCONCLUSIVE"
        metrics = {"frames": len(frames), "candidate_counts": counts,
                   "synthetic": args.synthetic, "hardware_tested": False,
                   "control_ready": False, "world_localization_tested": False}
        recorder.finish(result, metrics, "Synthetic expected counts checked." if args.synthetic else
            "Replay completed. No ground-truth labels supplied; detection accuracy is unassessed.")
        print(json.dumps({"result": result, "output": str(recorder.path.resolve()), **metrics}))
        return 1 if result == "FAIL" else 0
    except Exception as exc:
        recorder.event("error", {"type": type(exc).__name__, "message": str(exc)})
        recorder.finish("ABORTED", {"hardware_tested": False}, str(exc))
        print(f"ABORTED: {exc}; report: {recorder.path}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
