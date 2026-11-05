"""Pure-logic serial handoff. Process-local mutex; not a hardware zone lock."""
from dataclasses import dataclass
from threading import RLock
import math
import uuid


@dataclass(frozen=True)
class ZoneEvidence:
    observation_id: str
    stamp_s: float
    clock_domain: str
    occupied: bool | None
    left_clear: bool
    right_clear: bool

    def __post_init__(self):
        if (type(self.left_clear) is not bool or type(self.right_clear) is not bool
                or self.occupied is not None and type(self.occupied) is not bool):
            raise ValueError("explicit Boolean clearance/occupancy evidence required")


class HandoffFsm:
    def __init__(self, *, clock_domain, max_age_s):
        if not clock_domain or not math.isfinite(max_age_s) or max_age_s <= 0:
            raise ValueError("clock and evidence age required")
        self.clock_domain, self.max_age_s = clock_domain, max_age_s
        self.state = "EMPTY"
        self.owner = None
        self.token = None
        self.last_evidence_stamp = -1.
        self._lock = RLock()

    def _check(self, evidence, now_s):
        age = now_s - evidence.stamp_s
        if (not evidence.observation_id or evidence.clock_domain != self.clock_domain
                or not math.isfinite(age) or not 0 <= age <= self.max_age_s
                or evidence.stamp_s <= self.last_evidence_stamp):
            raise ValueError("fresh same-clock zone evidence required")
        if not evidence.left_clear or not evidence.right_clear or evidence.occupied is None:
            raise ValueError("both arms withdrawn and occupancy observed required")

    def reserve(self, side, evidence, *, now_s):
        with self._lock:
            if side not in {"left", "right"} or self.owner is not None:
                raise ValueError("shared region already owned or invalid side")
            self._check(evidence, now_s)
            if side == "left" and (self.state != "EMPTY" or evidence.occupied is not False):
                raise ValueError("left placement requires confirmed empty region")
            if side == "right" and (self.state != "OCCUPIED" or evidence.occupied is not True):
                raise ValueError("right pickup requires confirmed occupied region")
            self.owner, self.token = side, uuid.uuid4().hex
            self.state = "RESERVED_" + side.upper()
            self.last_evidence_stamp = evidence.stamp_s
            return self.token

    def enter(self, token):
        with self._lock:
            if token != self.token or self.owner is None or not self.state.startswith("RESERVED_"):
                raise ValueError("invalid zone lease")
            self.state = "LEFT_PLACING" if self.owner == "left" else "RIGHT_PICKING"

    def complete(self, token, evidence, *, now_s):
        with self._lock:
            if token != self.token or self.state not in {"LEFT_PLACING", "RIGHT_PICKING"}:
                raise ValueError("no matching active transfer")
            self._check(evidence, now_s)
            expected = self.owner == "left"
            if evidence.occupied is not expected:
                raise ValueError("zone occupancy does not prove completed transfer")
            self.state = "OCCUPIED" if expected else "EMPTY"
            self.owner = self.token = None
            self.last_evidence_stamp = evidence.stamp_s

    def fault(self):
        with self._lock:
            self.state = "RECOVERY"
            # Retain ownership: timeout/process error is not proof of clearance.

    def recover_after_observation(self, evidence, *, now_s):
        with self._lock:
            if self.state != "RECOVERY":
                raise ValueError("not recovering")
            self._check(evidence, now_s)
            self.state = "OCCUPIED" if evidence.occupied else "EMPTY"
            self.owner = self.token = None
            self.last_evidence_stamp = evidence.stamp_s
