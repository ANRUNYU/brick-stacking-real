"""Read-only camera and arm sources for the host monitor.

Camera and CAN access are optional and isolated. This module never enables
motors, sends trajectories, or constructs the P7 motion SDK.
"""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from typing import Any


HEAD_SERIAL_DEFAULT = "CP2L863000KL"
LEFT_ARM = ("left", "can2")
RIGHT_ARM = ("right", "can3")


@dataclass
class FramePacket:
    jpeg: bytes
    width: int
    height: int
    stamp_s: float
    camera_id: str
    source: str
    error: str | None = None


@dataclass
class ArmPacket:
    role: str
    channel: str
    joint_names: tuple[str, ...]
    q_rad: tuple[float | None, ...]
    validity: str
    reason: str | None
    stamp_s: float
    source: str
    error: str | None = None


@dataclass
class MonitorHub:
    frames: dict[str, FramePacket] = field(default_factory=dict)
    arms: dict[str, ArmPacket] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def set_frame(self, packet: FramePacket) -> None:
        with self.lock:
            self.frames[packet.camera_id] = packet

    def set_arm(self, packet: ArmPacket) -> None:
        with self.lock:
            self.arms[packet.role] = packet

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "meta": dict(self.meta),
                "cameras": {
                    cam_id: {
                        "camera_id": p.camera_id,
                        "width": p.width,
                        "height": p.height,
                        "stamp_s": p.stamp_s,
                        "source": p.source,
                        "error": p.error,
                        "has_jpeg": bool(p.jpeg),
                        "jpeg_bytes": len(p.jpeg),
                    }
                    for cam_id, p in self.frames.items()
                },
                "arms": {
                    role: {
                        "role": p.role,
                        "channel": p.channel,
                        "joint_names": list(p.joint_names),
                        "q_rad": list(p.q_rad),
                        "q_deg": [None if v is None else v * 180.0 / math.pi for v in p.q_rad],
                        "validity": p.validity,
                        "reason": p.reason,
                        "stamp_s": p.stamp_s,
                        "source": p.source,
                        "error": p.error,
                    }
                    for role, p in self.arms.items()
                },
                "host_monotonic_s": time.monotonic(),
            }

    def get_jpeg(self, camera_id: str) -> FramePacket | None:
        with self.lock:
            return self.frames.get(camera_id)


def _encode_jpeg(rgb, quality: int = 80) -> bytes:
    import cv2
    import numpy as np

    if rgb.dtype != np.uint8:
        raise ValueError("rgb must be uint8")
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
                           [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise RuntimeError("jpeg encode failed")
    return bytes(buf)


def _decode_rgb(data, encoding, width, height):
    import cv2
    import numpy as np

    raw = np.frombuffer(data, np.uint8)
    name = str(encoding).split(".")[-1]
    if name in {"RGB", "BGR"}:
        if raw.size != width * height * 3:
            raise ValueError("unexpected RGB size")
        image = raw.reshape(height, width, 3).copy()
        return image if name == "RGB" else image[:, :, ::-1].copy()
    if name == "MJPG":
        image = cv2.imdecode(raw, cv2.IMREAD_COLOR)
        if image is None or image.shape[:2] != (height, width):
            raise ValueError("invalid MJPEG frame")
        return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    if name == "YUYV":
        if raw.size != width * height * 2:
            raise ValueError("unexpected YUYV size")
        return cv2.cvtColor(raw.reshape(height, width, 2), cv2.COLOR_YUV2RGB_YUYV)
    raise ValueError(f"unsupported color encoding: {encoding}")


class MockCameraWorker(threading.Thread):
    def __init__(self, hub: MonitorHub, camera_id: str = "head", fps: float = 8.0):
        super().__init__(daemon=True, name=f"mock-cam-{camera_id}")
        self.hub = hub
        self.camera_id = camera_id
        self.period = 1.0 / max(fps, 1.0)
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        import numpy as np

        t0 = time.monotonic()
        while not self._stop.is_set():
            t = time.monotonic() - t0
            h, w = 360, 640
            yy, xx = np.mgrid[0:h, 0:w]
            rgb = np.zeros((h, w, 3), np.uint8)
            rgb[..., 0] = (80 + 40 * np.sin(t + xx / 80)).astype(np.uint8)
            rgb[..., 1] = (60 + 30 * np.cos(t * 0.7 + yy / 60)).astype(np.uint8)
            rgb[..., 2] = (40 + (xx // 8 + yy // 8) % 40).astype(np.uint8)
            cx, cy = int(w * (0.5 + 0.2 * math.sin(t))), int(h * (0.5 + 0.15 * math.cos(t * 1.3)))
            rgb[max(0, cy - 20):cy + 20, max(0, cx - 20):cx + 20] = (220, 90, 40)
            try:
                jpeg = _encode_jpeg(rgb, quality=70)
                self.hub.set_frame(FramePacket(jpeg, w, h, time.monotonic(), self.camera_id, "mock"))
            except Exception as exc:  # noqa: BLE001 - keep stream alive
                self.hub.set_frame(FramePacket(b"", 0, 0, time.monotonic(), self.camera_id, "mock", str(exc)))
            self._stop.wait(self.period)


class OrbbecCameraWorker(threading.Thread):
    """Hold one Orbbec device for preview until stop()/release."""

    def __init__(self, hub: MonitorHub, serial: str, camera_id: str = "head",
                 width: int = 640, height: int = 480, fps: int = 15, jpeg_quality: int = 75):
        super().__init__(daemon=True, name=f"orbbec-{camera_id}")
        self.hub = hub
        self.serial = serial
        self.camera_id = camera_id
        self.width = width
        self.height = height
        self.fps = fps
        self.jpeg_quality = jpeg_quality
        self._stop = threading.Event()
        self._released = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def wait_released(self, timeout_s: float = 5.0) -> bool:
        return self._released.wait(timeout_s)

    def run(self) -> None:
        pipe = None
        started = False
        try:
            import pyorbbecsdk as sdk

            context = sdk.Context()
            devices = context.query_devices()
            serials = [devices.get_device_serial_number_by_index(i) for i in range(devices.get_count())]
            if self.serial not in serials:
                raise ValueError(f"serial {self.serial} not enumerated; seen={serials}")
            device = devices.get_device_by_serial_number(self.serial)
            info = device.get_device_info()
            if info.get_serial_number() != self.serial:
                raise ValueError("opened serial mismatch")
            with self.hub.lock:
                self.hub.meta["camera_selected"] = {
                    "serial": info.get_serial_number(),
                    "name": info.get_name(),
                    "firmware": info.get_firmware_version(),
                }
                self.hub.meta.pop("camera_error", None)
                self.hub.meta.pop("camera_cleanup_error", None)
            pipe = sdk.Pipeline(device)
            cfg = sdk.Config()
            profile_list = pipe.get_stream_profile_list(sdk.OBSensorType.COLOR_SENSOR)
            color = profile_list.get_video_stream_profile(
                self.width, self.height, sdk.OBFormat.RGB, self.fps)
            cfg.enable_stream(color)
            pipe.start(cfg)
            started = True
            with self.hub.lock:
                self.hub.meta["camera_held"] = True
            while not self._stop.is_set():
                frames = pipe.wait_for_frames(100)
                if frames is None:
                    continue
                color_frame = frames.get_color_frame()
                if color_frame is None:
                    continue
                rgb = _decode_rgb(
                    bytes(color_frame.get_data()),
                    str(color_frame.get_format()),
                    color_frame.get_width(),
                    color_frame.get_height(),
                )
                jpeg = _encode_jpeg(rgb, self.jpeg_quality)
                self.hub.set_frame(FramePacket(
                    jpeg, rgb.shape[1], rgb.shape[0], time.monotonic(),
                    self.camera_id, "real_orbbec",
                ))
        except Exception as exc:  # noqa: BLE001
            self.hub.set_frame(FramePacket(
                b"", 0, 0, time.monotonic(), self.camera_id, "real_orbbec", str(exc),
            ))
            with self.hub.lock:
                self.hub.meta["camera_error"] = f"{type(exc).__name__}: {exc}"
                self.hub.meta["camera_held"] = False
        finally:
            if started and pipe is not None:
                try:
                    pipe.stop()
                except Exception as exc:  # noqa: BLE001
                    with self.hub.lock:
                        self.hub.meta["camera_cleanup_error"] = str(exc)
            with self.hub.lock:
                self.hub.meta["camera_held"] = False
            self._released.set()


class MockArmWorker(threading.Thread):
    def __init__(self, hub: MonitorHub, role: str = "left", period_s: float = 0.1):
        super().__init__(daemon=True, name=f"mock-arm-{role}")
        self.hub = hub
        self.role = role
        self.period_s = period_s
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        names = ("J1", "J2", "J3", "J4", "J5", "J6", "J7")
        t0 = time.monotonic()
        while not self._stop.is_set():
            t = time.monotonic() - t0
            q = tuple(0.2 * math.sin(t * 0.6 + i) for i in range(5)) + (None, None)
            self.hub.set_arm(ArmPacket(
                role=self.role,
                channel="mock",
                joint_names=names,
                q_rad=q,
                validity="PARTIAL",
                reason="mock J6/J7 unavailable like real read-only path",
                stamp_s=time.monotonic(),
                source="mock",
            ))
            self._stop.wait(self.period_s)


class ArmReaderWorker(threading.Thread):
    def __init__(self, hub: MonitorHub, role: str, channel: str, period_s: float = 0.15):
        super().__init__(daemon=True, name=f"arm-{role}")
        self.hub = hub
        self.role = role
        self.channel = channel
        self.period_s = period_s
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        try:
            from brick_stacking.arm.state import ArmStateReader, JOINTS
        except Exception as exc:  # noqa: BLE001
            self.hub.set_arm(ArmPacket(
                self.role, self.channel, ("J1", "J2", "J3", "J4", "J5", "J6", "J7"),
                (None,) * 7, "INVALID", str(exc), time.monotonic(), "real", str(exc),
            ))
            return
        try:
            with ArmStateReader.open(self.role, self.channel) as reader:
                while not self._stop.is_set():
                    try:
                        state = reader.read_state()
                        self.hub.set_arm(ArmPacket(
                            role=self.role,
                            channel=self.channel,
                            joint_names=tuple(state["joint_names"]),
                            q_rad=tuple(state["q_rad"]),
                            validity=state["validity"],
                            reason=state.get("reason"),
                            stamp_s=float(state["host_receive_stamp"]),
                            source="real",
                        ))
                    except Exception as exc:  # noqa: BLE001
                        self.hub.set_arm(ArmPacket(
                            self.role, self.channel, JOINTS, (None,) * 7,
                            "INVALID", str(exc), time.monotonic(), "real", str(exc),
                        ))
                    self._stop.wait(self.period_s)
        except Exception as exc:  # noqa: BLE001
            self.hub.set_arm(ArmPacket(
                self.role, self.channel, ("J1", "J2", "J3", "J4", "J5", "J6", "J7"),
                (None,) * 7, "INVALID", str(exc), time.monotonic(), "real", str(exc),
            ))
