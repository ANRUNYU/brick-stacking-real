"""Camera-only Orbbec inventory and bounded RGB-D capture, no robot imports.

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


def rectify_pair(rgb, depth_m, k, distortion):
    """Apply one common map to registered RGB/depth; do not fill depth holes."""
    import cv2
    import numpy as np
    model = distortion["model"].split(".")[-1]
    if model not in {"NONE", "BROWN_CONRADY", "BROWN_CONRADY_K6"}:
        raise ValueError(f"unverified distortion model: {model}")
    if rgb.shape[:2] != depth_m.shape:
        raise ValueError("D2C output must match color dimensions")
    names = ["k1", "k2", "p1", "p2", "k3", "k4", "k5", "k6"]
    d = np.array([distortion[n] for n in names], float)
    if not np.isfinite(d).all():
        raise ValueError("nonfinite camera distortion")
    if model == "NONE":
        if np.any(d != 0):
            raise ValueError("NONE model with nonzero coefficients")
        return rgb.copy(), depth_m.copy()
    if model == "BROWN_CONRADY":
        if np.any(d[5:] != 0):
            raise ValueError("Brown model has unverified extra coefficients")
        d = d[:5]
    h, w = depth_m.shape
    x, y = cv2.initUndistortRectifyMap(k, d, None, k, (w, h), cv2.CV_32FC1)
    return (cv2.remap(rgb, x, y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT),
            cv2.remap(depth_m, x, y, cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=float("nan")))


def describe_profile(profile):
    return {"width": profile.get_width(), "height": profile.get_height(),
            "fps": profile.get_fps(), "format": str(profile.get_format())}


def exposure_window_stable(samples):
    """Check recent RGB medians; also detects white balance shifts at equal Y."""
    import numpy as np
    values=np.asarray(samples,float)
    if len(values)<5:
        return False
    values=values[-5:]
    if values.shape!=(5,3) or not np.isfinite(values).all():
        raise ValueError('finite RGB median samples required')
    return bool(np.all(np.ptp(values,axis=0)<=np.maximum(2.,.03*np.median(values,axis=0))))


def choose_profile(profiles, formats, *, size=None, fps=None):
    candidates = []
    for i in range(profiles.get_count()):
        profile = profiles.get_stream_profile_by_index(i).as_video_stream_profile()
        if str(profile.get_format()).split(".")[-1] in formats:
            if size is not None and (profile.get_width(),profile.get_height()) != tuple(size):
                continue
            if fps is not None and profile.get_fps()!=fps:
                continue
            candidates.append(profile)
    if not candidates:
        raise ValueError("no supported stream profile matching explicit request; no fallback")
    # Modest initial bandwidth; actual selection is recorded, not guessed.
    return min(candidates, key=lambda p: (abs(p.get_width()-640)+abs(p.get_height()-480),
                                         abs(p.get_fps()-15), formats.index(str(p.get_format()).split(".")[-1])))


def capture(sdk, device, serial, output, report, *, count, seconds, max_skew_ms, size=None,
            fps=None, warmup_frames=30, on_frame=None, sdk_clock_type=None):
    import cv2
    import numpy as np
    pipe = sdk.Pipeline(device)
    started = False
    try:
        color = choose_profile(pipe.get_stream_profile_list(sdk.OBSensorType.COLOR_SENSOR), ["RGB", "MJPG", "YUYV", "BGR"],size=size,fps=fps)
        depth = choose_profile(pipe.get_stream_profile_list(sdk.OBSensorType.DEPTH_SENSOR), ["Y16"],size=size,fps=fps)
        report['requested_profiles']={'size_wh':size,'fps':fps,'explicit_request_has_no_fallback':True}
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
        previous_stamps = (-1., -1.)
        warmup = 0
        captured = 0
        missing = 0
        rgb_history=[]
        report['warmup_minimum_frames']=warmup_frames
        report['warmup_observations']=[]
        while captured < count and time.monotonic() < end:
            frames = pipe.wait_for_frames(1000)
            received = time.monotonic()
            if not frames:
                report["wait_timeouts"] = report.get("wait_timeouts", 0) + 1
                missing += 1
                if on_frame is not None and missing >= 2:
                    raise TimeoutError("Orbbec frames timed out")
                continue
            missing = 0
            clocks, clock_error = None, None
            if sdk_clock_type is not None:
                if __package__:
                    from .c_head_camera_probe import clock_anchor, frame_clocks
                else:
                    from c_head_camera_probe import clock_anchor, frame_clocks
                try:
                    original_color, original_depth = frames.get_color_frame(), frames.get_depth_frame()
                    if original_color and original_depth:
                        clocks = frame_clocks(original_color, original_depth, sdk_clock_type, clock_anchor())
                except (AttributeError, RuntimeError, ValueError) as exc:
                    clock_error = str(exc)
            aligned = align.process(frames)
            if not aligned:
                report["incomplete_pairs"] = report.get("incomplete_pairs", 0) + 1
                continue
            frames = aligned.as_frame_set()
            c, d = frames.get_color_frame(), frames.get_depth_frame()
            if not c or not d:
                report["incomplete_pairs"] = report.get("incomplete_pairs", 0) + 1
                continue
            warmup += 1
            ct, dt = c.get_timestamp_us()/1e6, d.get_timestamp_us()/1e6
            if abs(ct-dt)*1000 > max_skew_ms:
                report["rejected_skew"] += 1
                continue
            if ct <= previous_stamps[0] or dt <= previous_stamps[1]:
                raise ValueError("camera timestamp repeated or reset")
            previous_stamps = (ct, dt)
            w, h = c.get_width(), c.get_height()
            if (w, h) != (intr.width, intr.height):
                raise ValueError("stream/intrinsic resolution mismatch")
            rgb = decode_rgb(c.get_data(), str(c.get_format()), w, h)
            median_rgb=np.median(rgb.reshape(-1,3),axis=0).tolist()
            rgb_history.append(median_rgb)
            rgb_history=rgb_history[-5:]
            stable=exposure_window_stable(rgb_history)
            if not captured:
                report['warmup_observations'].append({'stamp_s':ct,'median_rgb':median_rgb,'stable_window':stable})
                if warmup<=warmup_frames or not stable:
                    continue
                report['capture_started_after_rgb_stabilization']=True
            elif not stable:
                report['exposure_changed_during_capture']=True
            if d.get_format() != sdk.OBFormat.Y16:
                raise ValueError("aligned depth is not Y16")
            raw = np.frombuffer(d.get_data(), np.uint16)
            if raw.size != d.get_width()*d.get_height():
                raise ValueError("unexpected depth row stride/size")
            scale_mm = d.get_depth_scale()
            dm = depth_to_metres(raw.reshape(d.get_height(),d.get_width()), scale_mm)
            if not captured and on_frame is None:
                cv2.imwrite(str(output/"color_raw.png"), cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
            rgb, dm = rectify_pair(rgb, dm, k, distortion)
            index = captured
            name = f"frame_{index:03d}.npz"
            meta = {"camera_id": serial, "frame_id": f"camera_{serial}_color_optical_frame", "stamp_s": ct,
                    "clock_domain": epoch, "source": "real_measured", "registered": True,
                    "rectified": True, "depth_unit": "m",
                    "host_receive_stamp_s": received, "host_clock_domain": "process_monotonic",
                    "depth_scale_mm": scale_mm, "rgb_device_stamp_s": ct, "depth_device_stamp_s": dt}
            if clocks is not None:
                meta["clock_observation"] = clocks
            if clock_error is not None:
                meta["clock_unavailable_reason"] = clock_error
            captured += 1
            if on_frame is not None:
                on_frame(rgb, dm, k, meta, report)
                continue
            np.savez_compressed(output/name, rgb=rgb, depth_m=dm, k=k, metadata=json.dumps(meta))
            valid = np.isfinite(dm) & (dm > 0)
            report["frames"].append({"file": name, "rgb_stamp_s": ct, "depth_stamp_s": dt,
                "skew_ms": abs(ct-dt)*1000, "depth_scale_mm": d.get_depth_scale(),
                "valid_depth_ratio": float(valid.mean()), "median_depth_m": float(np.median(dm[valid])) if valid.any() else None})
            if index == 0:
                cv2.imwrite(str(output/"color_rectified.png"), cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
                viz = np.zeros_like(dm, np.uint8)
                if valid.any():
                    lo, hi = np.percentile(dm[valid], [5,95])
                    viz[valid] = np.clip((dm[valid]-lo)/max(hi-lo,1e-6)*255,0,255).astype(np.uint8)
                cv2.imwrite(str(output/"depth_preview.png"), cv2.applyColorMap(viz,cv2.COLORMAP_TURBO))
        report["captured_pairs"] = captured
        report["result"] = "CAPTURED" if captured == count else "INCOMPLETE"
        report["notice"] = "Capture is not depth accuracy, alignment accuracy or block-detection acceptance. Clock is per-camera; no arm/world transform."
    finally:
        if started:
            try:
                pipe.stop()
            except Exception as exc:
                report["cleanup_errors"].append(str(exc))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--capture", action="store_true", help="otherwise inventory only")
    p.add_argument("--serial")
    p.add_argument("--uid", help="explicit enumerated USB UID if list serial is unavailable")
    p.add_argument("--frames", type=int, default=10)
    p.add_argument("--seconds", type=float, default=20)
    p.add_argument("--max-skew-ms", type=float, default=20)
    p.add_argument('--width',type=int,help='exact native stream width; requires --height')
    p.add_argument('--height',type=int,help='exact native stream height; requires --width')
    p.add_argument('--fps',type=int,help='exact stream frame rate, no fallback')
    p.add_argument('--warmup-frames',type=int,default=30,help='minimum startup frames, then wait for stable RGB medians')
    p.add_argument("--observe-profile", type=Path, help="run latest-pair tabletop detection during capture")
    p.add_argument("--max-receive-age-s", type=float, help="diagnostic receive-to-output limit")
    p.add_argument("--reconnects", type=int, default=0, help="bounded same-serial capture retries in observation mode")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    if args.output.exists():
        p.error("output exists; choose a fresh directory")
    if not 1 <= args.frames <= (900 if args.observe_profile else 50) or not 1 <= args.seconds <= 60 or not 0 < args.max_skew_ms <= 100:
        p.error("invalid capture bounds")
    if args.capture and not args.serial:
        p.error("capture requires explicit serial number")
    if (args.width is None)!=(args.height is None):
        p.error('--width and --height must be provided together')
    if args.width is not None and not (1<=args.width<=4096 and 1<=args.height<=4096):
        p.error('invalid requested image size')
    if args.fps is not None and not 1<=args.fps<=60:
        p.error('requested fps must be between 1 and 60')
    if not 5<=args.warmup_frames<=120:
        p.error('warmup frames must be between 5 and 120')
    if args.observe_profile and (not args.capture or args.fps is None or args.width is None
                                 or args.max_receive_age_s is None
                                 or not 0 < args.max_receive_age_s <= 60):
        p.error("observation mode requires capture, exact width/height/fps and a positive receive age")
    if not 0 <= args.reconnects <= 3 or (args.reconnects and not args.observe_profile):
        p.error("up to three retries are supported in observation mode")
    args.output.mkdir(parents=True)
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "scope": "camera_only",
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
            options = dict(count=args.frames, seconds=args.seconds, max_skew_ms=args.max_skew_ms,
                           size=(args.width,args.height) if args.width is not None else None,
                           fps=args.fps, warmup_frames=args.warmup_frames)
            if args.observe_profile:
                if __package__:
                    from .online_tabletop_observation import observe
                else:
                    from online_tabletop_observation import observe
                from brick_stacking.runtime.config_loader import load_config
                profile = load_config(args.observe_profile)
                if (profile["tabletop"]["camera_id"] != args.serial
                        or profile["tabletop"]["image_size_wh"] != [args.width, args.height]):
                    raise ValueError("requested serial/resolution differ from the observation profile")
                try:
                    sdk_clock_type = context.get_timestamp_clock_type()
                except (AttributeError, RuntimeError) as exc:
                    report["sdk_clock_unavailable_reason"] = str(exc)
                    sdk_clock_type = None

                def attempt(session, offer):
                    # Re-enumerate on every attempt, retaining the exact camera identity.
                    available = context.query_devices()
                    selected = available.get_device_by_serial_number(args.serial)
                    if selected.get_device_info().get_serial_number() != args.serial:
                        raise ValueError("reopened camera serial mismatch")
                    session["sdk_clock_unavailable_reason"] = report.get("sdk_clock_unavailable_reason")
                    capture(sdk, selected, args.serial, args.output, session, **options,
                            on_frame=offer, sdk_clock_type=sdk_clock_type)

                del device  # Release the inventory handle before the sole streaming owner opens.
                observe(args.output, report, profile, max_age_s=args.max_receive_age_s,
                        max_skew_s=args.max_skew_ms / 1000, reconnects=args.reconnects,
                        capture_attempt=attempt)
            else:
                capture(sdk, device, args.serial, args.output, report, **options)
        else:
            report["result"] = "INVENTORY" if report["devices"] else "NO_DEVICES"
    except Exception as exc:
        report["errors"].append(f"{type(exc).__name__}: {exc}")
        report["result"] = "ERROR"
    (args.output/"camera_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str,allow_nan=False),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,default=str,allow_nan=False))
    return 0 if report["result"] in {"INVENTORY","CAPTURED","OBSERVED"} and not report["cleanup_errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
