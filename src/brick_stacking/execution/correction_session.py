"""Offline accounting for one target's correction attempts, not an executor."""
from math import isfinite
from brick_stacking.planning.placement_review import Action, compare_effect


class CorrectionSession:
    def __init__(self, context, policy, *, started_s):
        if not isfinite(started_s) or started_s < 0:
            raise ValueError('finite monotonic start required')
        self.context, self.policy, self.started_s = context, policy, started_s
        self.attempts = 0
        self.total_push_m = 0.
        self.pending = None
        self.state = 'READY'
        self.events = []
        self.last_now_s = started_s
        self.used_observation_ids = set()

    def _time_ok(self, now_s):
        if not isfinite(now_s) or now_s < self.last_now_s:
            self.state = 'HALTED'
            return False
        self.last_now_s = now_s
        if now_s-self.started_s > self.policy.max_correction_s:
            self.state = 'HALTED'
            return False
        return True

    def stage(self, proposal, before, *, now_s):
        """Reserve a mock attempt. Caller must use a separate real Gate in future."""
        if not self._time_ok(now_s) or self.state != 'READY':
            raise ValueError('session not ready or expired')
        if (proposal.context != self.context or before.context != self.context or
                proposal.policy_id != self.policy.policy_id or
                proposal.observation_id != before.observation_id or
                before.observation_id in self.used_observation_ids or
                now_s-before.stamp_s < 0 or
                now_s-before.stamp_s > self.policy.max_observation_age_s or
                proposal.motion_enabled or proposal.permit is not None):
            self.state = 'HALTED'
            raise ValueError('proposal/evidence binding failed')
        if proposal.action not in (Action.PUSH, Action.REGRASP):
            raise ValueError('only correction proposals can be staged')
        if not isfinite(proposal.max_push_m) or (proposal.action == Action.REGRASP and proposal.max_push_m != 0):
            self.state = 'HALTED'
            raise ValueError('invalid displacement reservation')
        if self.attempts >= self.policy.max_attempts:
            self.state = 'HALTED'
            raise ValueError('attempt budget exhausted')
        if proposal.action == Action.PUSH and not (
                0 < proposal.max_push_m <= self.policy.max_push_step_m and
                self.total_push_m+proposal.max_push_m <= self.policy.max_total_push_m):
            self.state = 'HALTED'
            raise ValueError('push displacement budget exceeded')
        self.attempts += 1
        # Reserve the worst-case displacement now; failures must not refund it.
        self.total_push_m += proposal.max_push_m
        self.used_observation_ids.add(before.observation_id)
        self.pending = (proposal, before)
        self.state = 'WAITING_FOR_RESULT'

    def finish(self, after, *, now_s, execution_succeeded, actual_push_m,
               settled_and_retracted):
        if not self._time_ok(now_s) or self.state != 'WAITING_FOR_RESULT':
            raise ValueError('no pending attempt or expired')
        proposal, before = self.pending
        self.pending = None
        if (execution_succeeded is not True or settled_and_retracted is not True or
                not isfinite(actual_push_m) or actual_push_m < 0 or
                actual_push_m > proposal.max_push_m or
                now_s-after.stamp_s < 0 or now_s-after.stamp_s > self.policy.max_observation_age_s):
            verdict = 'EXECUTION_OR_RECHECK_FAILED'
        else:
            verdict = compare_effect(before, after, min_progress_m=self.policy.min_progress_m)
        if (verdict in ('IMPROVED', 'NO_CLEAR_PROGRESS') and
                all(e.upper <= b.stop for e,b in (
                    (after.xy_m,self.policy.xy_m), (after.height_m,self.policy.height_m),
                    (after.yaw_rad,self.policy.yaw_rad)))):
            verdict = 'TARGET_REACHED'
        self.state = ('COMPLETE' if verdict == 'TARGET_REACHED' else
                      'READY' if verdict == 'IMPROVED' else 'HALTED')
        self.events.append(dict(attempt=self.attempts, verdict=verdict,
                                before=before.observation_id, after=after.observation_id,
                                total_reserved_push_m=self.total_push_m,
                                motion_enabled=False))
        return verdict
