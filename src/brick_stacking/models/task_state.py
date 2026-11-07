from dataclasses import dataclass
from enum import Enum


class TaskStage(str, Enum):
    INIT = "INIT"
    OBSERVE = "OBSERVE"
    PLAN = "PLAN"
    PRE_GRASP = "PRE_GRASP"
    GRASP = "GRASP"
    VERIFY_PICK = "VERIFY_PICK"
    TRANSPORT = "TRANSPORT"
    PLACE = "PLACE"
    RETREAT = "RETREAT"
    VERIFY_PLACE = "VERIFY_PLACE"
    REOBSERVE = "REOBSERVE"
    FINAL_STABILITY_CHECK = "FINAL_STABILITY_CHECK"
    DONE = "DONE"
    SAFE_HALT = "SAFE_HALT"


@dataclass(frozen=True)
class TaskResult:
    stage: TaskStage
    verified_slots: tuple[str, ...]
    reason: str
    recovery_attempts: int
    manual_intervention_count: int = 0
    hardware_tested: bool = False
    reobservations: int = 0
