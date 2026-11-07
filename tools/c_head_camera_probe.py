"""Derived from host /home/qwer/orbbec_camera_probe.py, reviewed 2026-11-07.
Exact 1280x800@15 RGB/depth selection, no fallback.
Camera-only Orbbec inventory and bounded RGB-D capture, no robot imports.

Standalone on the Linux vision venv; helper functions are testable on Windows.
No firmware update, persistent property writes, CAN, arm/hand or motion access.
"""
import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import time
import uuid


def decode_rgb(data, encoding, width, height):
    import cv2
    import numpy as np
    raw = np.frombuffer(data, np.uint8)
    name = encoding.split(".")[-1]
    if name in {"RGB", "BGR"}:
        if raw.size != width * height * 3:
            raise ValueError("unexpected RGB row stride/size")
        image = raw.reshape(height, width, 3).copy()
        return image if name == "RGB" else image[:, :, ::-1].copy()
    if name == "MJPG":
        image = cv2.imdecode(raw, cv2.IMREAD_COLOR)
        if image is None or image.shape[:2] != (height, width):
            raise ValueError("invalid MJPEG frame")
        return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    if name == "YUYV":
        if raw.size != width * height * 2:
            raise ValueError("unexpected YUYV row stride/size")
        return cv2.cvtColor(raw.reshape(height, width, 2), cv2.COLOR_YUV2RGB_YUYV)
    raise ValueError(f"unsupported color encoding: {encoding}")


def depth_to_metres(raw, scale_mm):
    import numpy as np
    if not np.isfinite(scale_mm) or scale_mm <= 0:
        raise ValueError("invalid device depth scale")
    values = np.asarray(raw, np.float32) * scale_mm / 1000.
    values[~np.isfinite(values) | (values <= 0)] = np.nan
    return values


def rectify_pair(rgb, depth_m, k, distortion, *, map_cache=None, depth_distortion=None):
    """Rectify each aligned stream using its OWN distortion into common K.

    None depth_distortion retains the old helper convention for offline callers;
    real capture always supplies the aligned depth frame's explicit parameters.
    """
    import cv2
    import numpy as np
    if rgb.shape[:2] != depth_m.shape:
        raise ValueError("D2C output must match color dimensions")
    h, w = depth_m.shape
    def mapping(dist):
        model=dist["model"].split(".")[-1]
        if model not in {"NONE","BROWN_CONRADY","BROWN_CONRADY_K6"}:
            raise ValueError(f"unverified distortion model: {model}")
        d=np.array([dist[n] for n in ("k1","k2","p1","p2","k3","k4","k5","k6")],float)
        if not np.isfinite(d).all(): raise ValueError("nonfinite distortion")
        if model=="NONE" and np.any(d!=0): raise ValueError("NONE with nonzero distortion")
        if model=="BROWN_CONRADY":
            if np.any(d[5:]!=0): raise ValueError("unverified extra coefficients")
            d=d[:5]
        if not np.any(d): return None
        key=(w,h,k.tobytes(),d.tobytes())
        if map_cache is not None and key in map_cache: return map_cache[key]
        maps=cv2.initUndistortRectifyMap(k,d,None,k,(w,h),cv2.CV_32FC1)
        if map_cache is not None: map_cache[key]=maps
        return maps
    cm=mapping(distortion)
    dm=mapping(distortion if depth_distortion is None else depth_distortion)
    color=rgb.copy() if cm is None else cv2.remap(rgb,*cm,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
    depth=depth_m.copy() if dm is None else cv2.remap(depth_m,*dm,cv2.INTER_NEAREST,borderMode=cv2.BORDER_CONSTANT,borderValue=float("nan"))
    return color,depth


def describe_profile(profile):
    return {"width": profile.get_width(), "height": profile.get_height(),
            "fps": profile.get_fps(), "format": str(profile.get_format())}


def choose_profile(profiles, formats, *, width=1280, height=800, fps=15):
    """Exact dimensions and fps, format preference only; never silently downgrade."""
    candidates = []
    for i in range(profiles.get_count()):
        profile = profiles.get_stream_profile_by_index(i).as_video_stream_profile()
        name = str(profile.get_format()).split(".")[-1]
        if (profile.get_width(), profile.get_height(), profile.get_fps()) == (width, height, fps) and name in formats:
            candidates.append(profile)
    if not candidates:
        raise ValueError(f"requested {width}x{height}@{fps} unavailable; no fallback")
    return min(candidates, key=lambda p: formats.index(str(p.get_format()).split(".")[-1]))


def capture(sdk, device, serial, output, report, *, count, seconds, max_skew_ms):
    import cv2
    import numpy as np
    pipe = sdk.Pipeline(device)
    started = False
    pending = []
    map_cache = {}
    raw_preview = None
    try:
        color = choose_profile(pipe.get_stream_profile_list(sdk.OBSensorType.COLOR_SENSOR), ["RGB", "MJPG", "YUYV", "BGR"])
        depth = choose_profile(pipe.get_stream_profile_list(sdk.OBSensorType.DEPTH_SENSOR), ["Y16"])
        report["profiles"] = {"color": describe_profile(color), "depth": describe_profile(depth)}
        config = sdk.Config()
        config.enable_stream(color)
        config.enable_stream(depth)
        config.set_frame_aggregate_output_mode(sdk.OBFrameAggregateOutputMode.FULL_FRAME_REQUIRE)
        align = sdk.AlignFilter(align_to_stream=sdk.OBStreamType.COLOR_STREAM)
        align.set_match_target_resolution(True)
        pipe.enable_frame_sync()
        pipe.start(config)
        started = True
        intr = color.get_intrinsic()
        k = np.array([[intr.fx, 0., intr.cx], [0., intr.fy, intr.cy], [0., 0., 1.]])
        if not np.isfinite(k).all() or intr.fx <= 0 or intr.fy <= 0:
            raise ValueError("invalid device camera intrinsics")
        dist = color.get_distortion()
        distortion = {name: float(getattr(dist, name)) for name in ("k1", "k2", "k3", "k4", "k5", "k6", "p1", "p2")}
        distortion["model"] = str(dist.model)
        report["calibration"] = {"K": k.tolist(), "distortion": distortion,
                                 "width": intr.width, "height": intr.height, "extrinsics_available": False}
        epoch = f"orbbec_{serial}_{uuid.uuid4().hex}"
        end = time.monotonic() + seconds
        previous_stamp = -1.
        warmup = 0
        while len(report["frames"]) < count and time.monotonic() < end:
            wait_start = time.monotonic()
            frames = pipe.wait_for_frames(1000)
            host_receive_monotonic_s = time.monotonic()
            if not frames:
                continue
            align_start = time.monotonic()
            aligned = align.process(frames)
            align_end = time.monotonic()
            if not aligned:
                continue
            frames = aligned.as_frame_set()
            c, d = frames.get_color_frame(), frames.get_depth_frame()
            if not c or not d:
                continue
            warmup += 1
            if warmup <= 5:
                continue
            aligned_geometry = {}
            for label, frame in (("color", c), ("depth", d)):
                frame_profile = frame.get_stream_profile().as_video_stream_profile()
                fi = frame_profile.get_intrinsic()
                fd = frame_profile.get_distortion()
                fk = np.array([[fi.fx,0.,fi.cx],[0.,fi.fy,fi.cy],[0.,0.,1.]])
                aligned_geometry[label] = {"K": fk.tolist(), "width": fi.width, "height": fi.height,
                    "distortion": {name: float(getattr(fd,name)) for name in ("k1","k2","k3","k4","k5","k6","p1","p2")},
                    "distortion_model": str(fd.model)}
                if (fi.width,fi.height)!=(intr.width,intr.height) or not np.allclose(fk,k,atol=1e-5,rtol=0):
                    report["aligned_geometry"] = aligned_geometry
                    raise ValueError("aligned frame K/dimensions differ; refusing old-intrinsic backprojection")
            report["aligned_geometry"] = aligned_geometry
            ct, dt = c.get_timestamp_us()/1e6, d.get_timestamp_us()/1e6
            if abs(ct-dt)*1000 > max_skew_ms:
                report["rejected_skew"] += 1
                continue
            if ct <= previous_stamp:
                raise ValueError("camera timestamp repeated or reset")
            previous_stamp = ct
            w, h = c.get_width(), c.get_height()
            if (w, h) != (intr.width, intr.height):
                raise ValueError("stream/intrinsic resolution mismatch")
            decode_start = time.monotonic()
            rgb = decode_rgb(c.get_data(), str(c.get_format()), w, h)
            if d.get_format() != sdk.OBFormat.Y16:
                raise ValueError("aligned depth is not Y16")
            raw = np.frombuffer(d.get_data(), np.uint16)
            if raw.size != d.get_width()*d.get_height():
                raise ValueError("unexpected depth row stride/size")
            dm = depth_to_metres(raw.reshape(d.get_height(),d.get_width()), d.get_depth_scale())
            if not report["frames"]:
                raw_preview = rgb.copy()
            decode_end = time.monotonic()
            frame_depth_distortion = dict(aligned_geometry["depth"]["distortion"])
            frame_depth_distortion["model"] = aligned_geometry["depth"]["distortion_model"]
            frame_color_distortion = dict(aligned_geometry["color"]["distortion"])
            frame_color_distortion["model"] = aligned_geometry["color"]["distortion_model"]
            rgb, dm = rectify_pair(rgb, dm, k, frame_color_distortion, map_cache=map_cache,
                                   depth_distortion=frame_depth_distortion)
            rectify_end = time.monotonic()
            index = len(report["frames"])
            name = f"frame_{index:03d}.npz"
            meta = {"camera_id": serial, "frame_id": f"camera_{serial}_color_optical_frame", "stamp_s": ct,
                    "clock_domain": epoch, "source": "real_measured",
                    "host_receive_stamp_s": host_receive_monotonic_s, "host_clock_domain": "host_monotonic", "registered": True,
                    "rectified": True, "depth_unit": "m"}
            pending.append((name, rgb, dm, meta))
            valid = np.isfinite(dm) & (dm > 0)
            report["frames"].append({"file": name, "rgb_stamp_s": ct, "depth_stamp_s": dt,
                "skew_ms": abs(ct-dt)*1000, "depth_scale_mm": d.get_depth_scale(),
                "timing_s": {"wait": host_receive_monotonic_s-wait_start, "align": align_end-align_start, "decode_depth": decode_end-decode_start, "rectify": rectify_end-decode_end},
                "host_receive_stamp_s": host_receive_monotonic_s, "host_clock_domain": "host_monotonic",
                "valid_depth_ratio": float(valid.mean()), "median_depth_m": float(np.median(dm[valid])) if valid.any() else None})
        report["result"] = "CAPTURED" if len(report["frames"]) == count else "INCOMPLETE"
        report["notice"] = "Capture is not depth accuracy, alignment accuracy or block-detection acceptance. Clock is per-camera; no arm/world transform."
    finally:
        if started:
            try:
                pipe.stop()
            except Exception as exc:
                report["cleanup_errors"].append(str(exc))
    # Pipeline is stopped before compression, disk writes and previews.
    persistence_start = time.monotonic()
    for name, rgb, dm, meta in pending:
        np.savez_compressed(output/name, rgb=rgb, depth_m=dm, k=k, metadata=json.dumps(meta))
    report["persistence_after_stop_s"] = time.monotonic()-persistence_start
    if pending:
        _, rgb, dm, _ = pending[0]
        cv2.imwrite(str(output/"color_raw.png"), cv2.cvtColor(raw_preview,cv2.COLOR_RGB2BGR))
        cv2.imwrite(str(output/"color_rectified.png"), cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
    report["timing_note"] = "Compression/write/previews deferred until pipe.stop; bounded RAM capture, not long-run recorder. Host receive clock is not device clock."



def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--capture", action="store_true", help="otherwise inventory only")
    p.add_argument("--serial")
    p.add_argument("--uid", help="explicit enumerated USB UID if list serial is unavailable")
    p.add_argument("--frames", type=int, default=10)
    p.add_argument("--seconds", type=float, default=20)
    p.add_argument("--max-skew-ms", type=float, default=20)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    if args.output.exists():
        p.error("output exists; choose a fresh directory")
    if not 1 <= args.frames <= 50 or not 1 <= args.seconds <= 60 or not 0 < args.max_skew_ms <= 100:
        p.error("invalid capture bounds")
    if args.capture and not args.serial:
        p.error("capture requires explicit serial number")
    args.output.mkdir(parents=True)
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "scope": "camera_only", "tool_version": "c-head-1280x800-15-v4-separate-distortion",
        "robot_motion_accessed": False, "can_accessed": False, "devices": [],
        "frames": [], "rejected_skew": 0, "errors": [], "cleanup_errors": [], "result": "ERROR"}
    try:
        import pyorbbecsdk as sdk
        report["binding_version"] = importlib.metadata.version("pyorbbecsdk2")
        report["sdk_version"] = sdk.get_version()
        context = sdk.Context()
        devices = context.query_devices()
        for i in range(devices.get_count()):
            report["devices"].append({"serial": devices.get_device_serial_number_by_index(i),
                "name": devices.get_device_name_by_index(i), "uid": devices.get_device_uid_by_index(i)})
        if args.capture:
            if args.uid:
                if args.uid not in {d["uid"] for d in report["devices"]}:
                    raise ValueError("requested UID not enumerated; no camera fallback")
                device = devices.get_device_by_uid(args.uid)
            else:
                if args.serial not in {d["serial"] for d in report["devices"]}:
                    raise ValueError("requested camera not enumerated; no fallback to another camera")
                device = devices.get_device_by_serial_number(args.serial)
            info = device.get_device_info()
            report["selected"] = {"serial": info.get_serial_number(), "name": info.get_name(),
                                  "firmware": info.get_firmware_version(), "connection": info.get_connection_type()}
            if report["selected"]["serial"] != args.serial:
                raise ValueError("opened device serial does not match explicit requested serial")
            capture(sdk,device,args.serial,args.output,report,count=args.frames,seconds=args.seconds,max_skew_ms=args.max_skew_ms)
        else:
            report["result"] = "INVENTORY" if report["devices"] else "NO_DEVICES"
    except Exception as exc:
        report["errors"].append(f"{type(exc).__name__}: {exc}")
        report["result"] = "ERROR"
    (args.output/"camera_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str,allow_nan=False),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,default=str,allow_nan=False))
    return 0 if report["result"] in {"INVENTORY","CAPTURED"} and not report["cleanup_errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
