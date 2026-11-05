"""Mock transitions are software fixtures; no CAN, ROS, or SDK imports."""
import json
from pathlib import Path
import numpy as np
from brick_stacking.models.camera_frame import CameraFrame


class RecordedCamera:
    """Small explicit NPZ format, not a rosbag2 reader. Units are never guessed."""
    def __init__(self, paths):
        self._paths = iter(paths)

    def get_synced_rgbd(self):
        path = Path(next(self._paths))
        with np.load(path, allow_pickle=False) as data:
            meta = json.loads(str(data["metadata"].item()))
            if meta.pop("depth_unit") != "m":
                raise ValueError("recording must contain depth in metres")
            return CameraFrame(data["rgb"], data["depth_m"], data["k"], **meta)


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

    def __init__(self):
        self._preset = "UNKNOWN"

    def simulate_preset(self, name):
        if name not in {"MOCK_OPEN", "MOCK_HOLD"}:
            raise ValueError("mock presets only; no real gesture calibration")
        self._preset = name

    def get_state(self):
        return {"preset": self._preset, "source": "synthetic", "contact_confirmed": False}

    def stop(self):
        self._preset = "MOCK_STOPPED"
