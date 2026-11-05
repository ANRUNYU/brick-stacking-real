"""Immutable scene contracts for the offline transaction framework."""
from dataclasses import dataclass
from enum import Enum
import math


class BlockLocation(str, Enum):
    SUPPLY = "SUPPLY"
    HELD_LEFT = "HELD_LEFT"
    HELD_RIGHT = "HELD_RIGHT"
    PLACED = "PLACED"
    UNKNOWN = "UNKNOWN"


class SlotState(str, Enum):
    EMPTY = "EMPTY"
    RESERVED = "RESERVED"
    PLACED_VERIFIED = "PLACED_VERIFIED"
    UNVERIFIED = "UNVERIFIED"


@dataclass(frozen=True)
class SceneBlock:
    object_id: str
    color: str
    center_m: tuple[float, float, float]
    frame_id: str
    location: BlockLocation = BlockLocation.SUPPLY
    visible: bool = True
    ambiguous: bool = False

    def __post_init__(self):
        if not self.object_id or not self.frame_id or len(self.center_m) != 3 or not all(map(math.isfinite, self.center_m)):
            raise ValueError("identified finite block pose required")
        if self.color not in {"red", "yellow", "blue", "green", "unknown"}:
            raise ValueError("unknown color label")


@dataclass(frozen=True)
class Slot:
    slot_id: str
    layer: int
    required_color: str
    center_m: tuple[float, float, float]
    frame_id: str
    supports: tuple[str, ...]


@dataclass(frozen=True)
class SceneSnapshot:
    observation_id: str
    epoch: str
    stamp_s: float
    clock_domain: str
    blocks: tuple[SceneBlock, ...]
    hand_clear: bool
    source: str

    def __post_init__(self):
        if not self.observation_id or not self.epoch or not self.clock_domain or not self.source:
            raise ValueError("snapshot identity/provenance required")
        if not math.isfinite(self.stamp_s) or self.stamp_s < 0:
            raise ValueError("invalid observation timestamp")
        ids = [b.object_id for b in self.blocks]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate object identity")
