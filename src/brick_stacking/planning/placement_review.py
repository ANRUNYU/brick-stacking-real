"""Offline placement review policy. Proposals are not motion commands or permits.

V owns extraction of these measurements. M consumes explicit error bounds; no
Gaussian confidence, latency bound, table frame or contact capability is inferred.
"""
from dataclasses import dataclass
from enum import Enum
from math import isfinite


class Action(str, Enum):
    ACCEPT = 'ACCEPT'
    OBSERVE = 'OBSERVE'
    PUSH = 'PUSH_PROPOSAL'
    REGRASP = 'REGRASP_PROPOSAL'
    HALT = 'HALT'


@dataclass(frozen=True)
class ErrorBound:
    value: float
    bound: float

    def __post_init__(self):
        if not all(isfinite(x) and x >= 0 for x in (self.value, self.bound)):
            raise ValueError('nonnegative finite absolute error and bound required')

    @property
    def lower(self):
        return max(0., self.value - self.bound)

    @property
    def upper(self):
        return self.value + self.bound


@dataclass(frozen=True)
class Band:
    """One metric, in its declared unit: stop < trigger <= acceptance."""
    stop: float
    trigger: float
    acceptance: float

    def __post_init__(self):
        if not all(isfinite(x) for x in (self.stop, self.trigger, self.acceptance)):
            raise ValueError('finite thresholds required')
        if not 0 < self.stop < self.trigger <= self.acceptance:
            raise ValueError('require 0 < stop < trigger <= acceptance')


@dataclass(frozen=True)
class ReviewPolicy:
    policy_id: str
    xy_m: Band
    height_m: Band
    yaw_rad: Band
    max_push_step_m: float
    max_total_push_m: float
    max_attempts: int
    max_correction_s: float
    min_progress_m: float
    max_observation_age_s: float
    max_extra_views: int

    def __post_init__(self):
        positive = (self.max_push_step_m, self.max_total_push_m,
                    self.max_correction_s, self.min_progress_m, self.max_observation_age_s)
        if not self.policy_id or not all(isfinite(x) and x > 0 for x in positive):
            raise ValueError('explicit versioned finite policy required')
        if self.max_total_push_m < self.max_push_step_m:
            raise ValueError('total displacement budget smaller than one step')
        if type(self.max_attempts) is not int or self.max_attempts < 1:
            raise ValueError('positive integer attempts required')
        if type(self.max_extra_views) is not int or not 0 <= self.max_extra_views <= 2:
            raise ValueError('zero to two extra sequential views supported')


@dataclass(frozen=True)
class Context:
    target_id: str
    scope: str  # block or layer
    frame_id: str
    scene_version: str
    calibration_hash: str
    profile_hash: str
    epoch: str
    clock_domain: str

    def __post_init__(self):
        if self.scope not in ('block', 'layer') or not all(
                isinstance(x, str) and x for x in self.__dict__.values()):
            raise ValueError('complete immutable review context required')


@dataclass(frozen=True)
class Inspection:
    context: Context
    observation_id: str
    stamp_s: float  # same monotonic domain as caller now_s
    xy_m: ErrorBound
    height_m: ErrorBound
    yaw_rad: ErrorBound
    color_ok: bool | None
    support_ok: bool | None
    stable: bool | None
    hand_clear: bool
    visible: bool
    neighbors_unchanged: bool | None

    def __post_init__(self):
        if not self.observation_id or not isfinite(self.stamp_s) or self.stamp_s < 0:
            raise ValueError('observation ID and finite monotonic stamp required')
        for name in ('color_ok', 'support_ok', 'stable', 'neighbors_unchanged'):
            if getattr(self, name) is not None and type(getattr(self, name)) is not bool:
                raise ValueError('evidence must be bool or None')
        if type(self.hand_clear) is not bool or type(self.visible) is not bool:
            raise ValueError('visibility and hand clearance must be explicit')


@dataclass(frozen=True)
class TimeBudget:
    remaining_s: float
    mandatory_work_s: float
    reserve_s: float
    observe_s: float
    push_cycle_s: float
    regrasp_cycle_s: float
    # Cycle estimates include approach, action, release/retract, settle and recheck.

    def __post_init__(self):
        if not all(isfinite(x) and x >= 0 for x in self.__dict__.values()):
            raise ValueError('finite nonnegative measured time estimates required')
        if min(self.observe_s, self.push_cycle_s, self.regrasp_cycle_s) <= 0:
            raise ValueError('zero-time operations are not valid estimates')

    def allows(self, seconds):
        return self.remaining_s >= self.mandatory_work_s + self.reserve_s + seconds


@dataclass(frozen=True)
class PushEligibility:
    """Facts supplied by validated contact/scene planning, not guessed by review."""
    response_model_id: str | None = None
    contact_plan_id: str | None = None
    bottom_layer: bool = False
    isolated: bool = False
    side_access_clear: bool = False
    contact_control_validated: bool = False
    collision_checked: bool = False
    translation_only: bool = False

    def __post_init__(self):
        for name in ('bottom_layer', 'isolated', 'side_access_clear',
                     'contact_control_validated', 'collision_checked', 'translation_only'):
            if type(getattr(self, name)) is not bool:
                raise ValueError('push validation facts must be explicit booleans')
        for item in (self.response_model_id, self.contact_plan_id):
            if item is not None and (not isinstance(item, str) or not item):
                raise ValueError('nonempty versioned response/contact IDs required')

    @property
    def eligible(self):
        return bool(self.response_model_id and self.contact_plan_id and all((
            self.bottom_layer, self.isolated, self.side_access_clear,
            self.contact_control_validated, self.collision_checked, self.translation_only)))


@dataclass(frozen=True)
class Proposal:
    action: Action
    reason: str
    policy_id: str
    observation_id: str
    context: Context
    max_push_m: float = 0.
    view_number: int = 0
    motion_enabled: bool = False
    permit: None = None


def review(inspection, policy, budget, *, now_s, expected_context,
           correcting=False, extra_views=0, push=None, regrasp_validated=False):
    """Pick an offline suggestion. No hardware adapter, IK or Gate is invoked."""
    if type(extra_views) is not int or extra_views < 0:
        raise ValueError('nonnegative extra view count required')
    if type(correcting) is not bool or type(regrasp_validated) is not bool:
        raise ValueError('explicit mode/capability flags required')
    def result(action, reason, **kwargs):
        return Proposal(action, reason, policy.policy_id, inspection.observation_id,
                        inspection.context, **kwargs)
    if not isfinite(now_s) or inspection.context != expected_context:
        return result(Action.HALT, 'CONTEXT_OR_CLOCK_MISMATCH')
    age = now_s - inspection.stamp_s
    if age < 0 or age > policy.max_observation_age_s:
        return result(Action.HALT, 'STALE_OR_FUTURE_OBSERVATION')
    if inspection.stable is False or inspection.support_ok is False:
        return result(Action.HALT, 'UNSTABLE_OR_UNSUPPORTED')
    if inspection.neighbors_unchanged is False:
        return result(Action.HALT, 'NEIGHBOR_DISTURBANCE')

    def observe(reason):
        if extra_views >= policy.max_extra_views:
            return result(Action.HALT, 'VIEW_LIMIT:'+reason)
        if not budget.allows(budget.observe_s):
            return result(Action.HALT, 'INSUFFICIENT_TIME_FOR_EVIDENCE')
        return result(Action.OBSERVE, reason, view_number=extra_views + 1)

    if (not inspection.visible or not inspection.hand_clear or
            any(x is None for x in (inspection.stable, inspection.support_ok,
                                   inspection.color_ok, inspection.neighbors_unchanged))):
        return observe('INCOMPLETE_EVIDENCE')
    metrics = ((inspection.xy_m, policy.xy_m), (inspection.height_m, policy.height_m),
               (inspection.yaw_rad, policy.yaw_rad))
    # A correction session uses the tighter stop band: hysteresis, no zero chasing.
    if inspection.color_ok and all(e.upper <= (b.stop if correcting else b.trigger)
                                   for e, b in metrics):
        return result(Action.ACCEPT, 'INSIDE_STOP_BAND' if correcting else 'INSIDE_TRIGGER_BAND')
    confirmed = not inspection.color_ok or any(e.lower > b.trigger for e, b in metrics)
    if not confirmed and not correcting:
        return observe('THRESHOLD_OVERLAPS_MEASUREMENT_BOUND')
    # For now, rotation/height correction and layer-level motion are regrasp-only.
    push_safe = (inspection.context.scope == 'block' and inspection.color_ok and
                 inspection.height_m.upper <= policy.height_m.stop and
                 inspection.yaw_rad.upper <= policy.yaw_rad.stop and
                 inspection.xy_m.lower > policy.xy_m.stop and push is not None and push.eligible)
    choices = []
    if push_safe and budget.allows(budget.push_cycle_s):
        choices.append((budget.push_cycle_s, Action.PUSH))
    if (inspection.context.scope == 'block' and regrasp_validated and
            budget.allows(budget.regrasp_cycle_s)):
        choices.append((budget.regrasp_cycle_s, Action.REGRASP))
    if choices:
        _, action = min(choices, key=lambda item: item[0])
        # A bound, not a displacement command. Contact model must pick the actual step.
        step = min(policy.max_push_step_m, max(0., inspection.xy_m.lower-policy.xy_m.stop))
        return result(action, 'VALIDATED_STRATEGY_WITHIN_TIME',
                      max_push_m=step if action == Action.PUSH else 0.)
    if (inspection.color_ok and all(e.upper <= b.acceptance for e,b in metrics)):
        return result(Action.ACCEPT, 'ACCEPTABLE_WITHOUT_OPTIONAL_REFINEMENT')
    return result(Action.HALT, 'NO_VALIDATED_CORRECTION_WITHIN_TIME')


def compare_effect(before, after, *, min_progress_m):
    """Require improvement exceeding both declared bounds; never auto reverse."""
    if not isfinite(min_progress_m) or min_progress_m <= 0:
        raise ValueError('positive progress threshold required')
    if (before.context != after.context or before.observation_id == after.observation_id
            or after.stamp_s <= before.stamp_s):
        return 'INVALID_EVIDENCE'
    if not after.visible or not after.hand_clear or any(x is not True for x in (
            after.stable, after.support_ok, after.color_ok, after.neighbors_unchanged)):
        return 'UNSAFE_OR_UNKNOWN'
    pairs = ((before.xy_m, after.xy_m), (before.height_m, after.height_m),
             (before.yaw_rad, after.yaw_rad))
    if any(a.lower > b.upper for b,a in pairs):
        return 'WORSENED'
    return 'IMPROVED' if before.xy_m.lower-after.xy_m.upper >= min_progress_m else 'NO_CLEAR_PROGRESS'
