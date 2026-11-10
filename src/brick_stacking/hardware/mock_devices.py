"""Mock transitions are software fixtures; no CAN, ROS, or SDK imports."""
import json
from pathlib import Path
import time
from typing import cast
from uuid import uuid4

import numpy as np

from brick_stacking.contracts import HandChannels, HandRole, HandState
from brick_stacking.models.camera_frame import CameraFrame


class RecordedCamera:
    """Small explicit NPZ format, not a rosbag2 reader. Units are never guessed."""
    def __init__(self, paths):
        self._paths = iter(paths)

    def get_synced_rgbd(self):
        frame, _ = self.read_recording(next(self._paths))
        return frame

    @staticmethod
    def read_recording(path):
        path = Path(path)
        with np.load(path, allow_pickle=False) as data:
            meta = json.loads(str(data["metadata"].item()))
            if meta["depth_unit"] != "m":
                raise ValueError("recording must contain depth in metres")
            fields = ("camera_id", "frame_id", "stamp_s", "clock_domain", "source",
                      "registered", "rectified")
            frame = CameraFrame(data["rgb"], data["depth_m"], data["k"],
                                **{field: meta[field] for field in fields})
            return frame, meta


class MockArm:
    hardware_enabled = False

    def __init__(self, initial_joints_rad):
        self._joints = tuple(initial_joints_rad)
        if not self._joints or not np.isfinite(self._joints).all():
            raise ValueError("explicit finite initial joints required")
        self.events = []

    def get_joint_state(self):
        return self._joints

    def simulate_joint_target(self, joints_rad):
        values = tuple(joints_rad)
        if len(values) != len(self._joints) or not np.isfinite(values).all():
            raise ValueError("invalid mock target")
        self._joints = values
        self.events.append({"kind": "mock_target", "physical_execution": False})

    def stop(self):
        self.events.append({"kind": "mock_stop", "physical_execution": False})


class MockHand:
    hardware_enabled = False

    def __init__(
        self,
        *,
        role: HandRole = "left",
        raw_u8: HandChannels = (0, 0, 0, 0, 0, 0),
    ):
        if role not in ("left", "right"):
            raise ValueError("select left or right")
        values = tuple(raw_u8)
        if len(values) != 6 or any(type(value) is not int or not 0 <= value <= 255 for value in values):
            raise ValueError("mock hand requires six raw_u8 channels in [0, 255]")
        self._role = role
        self._raw_u8 = cast(HandChannels, values)
        self._epoch = uuid4().hex
        self._preset = "UNKNOWN"

    def read_hand_state(self) -> HandState:
        serial = f"mock-o6-{self._role}"
        return {
            "sample_id": uuid4().hex,
            "source": "mock",
            "device_id": serial,
            "frame_id": f"{self._role}_hand",
            "device_stamp": None,
            "host_receive_stamp": time.monotonic(),
            "clock_domain": "host_monotonic",
            "epoch": self._epoch,
            "validity": "VALID",
            "reason": None,
            "role": self._role,
            "hand_sn": serial,
            "raw_u8": self._raw_u8,
            "mapping_version": "mock-raw-u8-v1",
            "fault_valid": False,
            "temperature_valid": False,
            "tactile_valid": False,
        }

    def simulate_preset(self, name):
        if name not in {"MOCK_OPEN", "MOCK_HOLD"}:
            raise ValueError("mock presets only; no real gesture calibration")
        self._preset = name

    def get_state(self):
        return {"preset": self._preset, "source": "synthetic", "contact_confirmed": False}

    def stop(self):
        self._preset = "MOCK_STOPPED"
