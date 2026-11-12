"""Issue 37 stationary capture: query feedback while the camera-only probe records.

Run on the robot host with the P7 SDK Python. Host receipt and SDK read times
are evidence of temporal proximity only; raw motor/device sample age is unknown.
"""
import argparse
from contextlib import ExitStack
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import subprocess
import time


def timed_read(fn, size):
    start = time.monotonic()
    values = list(map(float, fn()))
    end = time.monotonic()
    if len(values) != size or not all(map(math.isfinite, values)):
        raise ValueError("invalid feedback vector")
    return {"host_begin_s": start, "host_end_s": end, "values": values}


def run(args):
    from linkerbot import O6, P7
    args.output.mkdir(exist_ok=False, parents=True)
    report = dict(utc=datetime.now(timezone.utc).isoformat(), motion_commanded=False,
                  control_ready=False, scene_ready=False, camera="CP2L863000KL",
                  left_arm="can2", right_arm="can3", left_hand="can1", errors=[])
    try:
        with ExitStack() as stack:
            arms = {}
            for side, iface in (("left","can2"), ("right","can3")):
                arm = P7(side=side, interface_name=iface)
                stack.callback(arm.close)
                arms[side] = arm
            hand = O6(side="left", interface_name="can1")
            stack.callback(hand.close)
            hand.stop_polling()
            info = hand.version.get_device_info()
            report["hand_info"] = asdict(info) if is_dataclass(info) else str(info)
            if "LHO6-04-322-L-Z-1-D" not in str(report["hand_info"]):
                raise ValueError("left hand identity unconfirmed")
            def sample():
                row = {side: timed_read(arm.get_angles, 7) for side, arm in arms.items()}
                msg = hand.angle.get_blocking(timeout_ms=500)
                row["hand"] = dict(values=list(map(float, msg.angles.to_list())),
                                   sdk_timestamp_s=float(msg.timestamp), host_end_s=time.monotonic(),
                                   unit="sdk_percent_not_urdf_rad")
                if len(row["hand"]["values"]) != 6 or not all(math.isfinite(v) for v in row["hand"]["values"]):
                    raise ValueError("invalid hand feedback")
                return row
            with (args.output/"samples.jsonl").open("x") as data:
                def record():
                    data.write(json.dumps(sample(), allow_nan=False)+"\n")
                    data.flush()
                record()
                cmd = [str(args.camera_python), str(args.probe), "--capture", "--serial", report["camera"],
                       "--width","640","--height","480","--fps","15","--warmup-frames","30",
                       "--allow-unstable-warmup","--fixed-color-exposure","24","--fixed-color-gain","12",
                       "--frames","10","--seconds","30","--output",str(args.output/"rgbd")]
                with (args.output/"probe.log").open("xb") as log:
                    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
                    deadline = time.monotonic()+60
                    try:
                        while proc.poll() is None:
                            record()
                            if time.monotonic() >= deadline:
                                raise TimeoutError("camera process timed out")
                            time.sleep(.08)
                        if proc.returncode: raise RuntimeError(f"camera exit {proc.returncode}")
                    finally:
                        if proc.poll() is None:
                            proc.terminate()
                            try: proc.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                proc.kill()
                                proc.wait()
                record()
            camera = json.loads((args.output/"rgbd/camera_report.json").read_bytes())
            if camera["result"] != "CAPTURED" or camera["captured_pairs"] != 10:
                raise ValueError("camera capture incomplete")
            report["capture_status"] = "CAPTURED_FOR_REVIEW"
    except Exception as exc:
        report["errors"].append(f"{type(exc).__name__}: {exc}")
        report["capture_status"] = "INCOMPLETE"
    finally:
        (args.output/"summary.json").write_text(json.dumps(report, indent=2, default=str)+"\n")
    print(json.dumps(report, default=str))
    return int(bool(report["errors"]))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--probe", type=Path, required=True)
    p.add_argument("--camera-python", type=Path, required=True)
    raise SystemExit(run(p.parse_args()))
