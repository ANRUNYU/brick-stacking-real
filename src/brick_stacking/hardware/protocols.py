"""Project contracts, not vendor API names. Hardware implementation deferred."""
from typing import Protocol
from brick_stacking.models.camera_frame import CameraFrame


class CameraAdapter(Protocol):
    def get_synced_rgbd(self) -> CameraFrame: ...


class ArmAdapter(Protocol):
    def get_joint_state(self) -> tuple[float, ...]: ...
    def stop(self) -> None: ...


class HandAdapter(Protocol):
    def get_state(self) -> dict: ...
    def stop(self) -> None: ...

# No production execution method until stop/feedback/planning capabilities are
# audited. Mock-only commands below must not be mistaken for hardware methods.
