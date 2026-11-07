"""Offline stop-at-waypoint quintic trajectories, contract c-trajectory-1.

No IK, robot identity verification, collision checking or execution permission.
All joints use rad; times use seconds in an explicitly named clock/epoch.
"""
from dataclasses import dataclass
import math
import numpy as np


def _vector(values, n, name):
    a = np.asarray(values, dtype=float)
    if a.shape != (n,) or not np.isfinite(a).all():
        raise ValueError(f'{name}: finite vector matching joint_names required')
    return a


def _names(names):
    names = tuple(names)
    if not names or any(not isinstance(n, str) or not n.strip() for n in names) or len(set(names)) != len(names):
        raise ValueError('unique explicit joint names required')
    return names


@dataclass(frozen=True)
class JointLimits:
    joint_names: tuple[str, ...]
    lower_rad: tuple[float, ...]
    upper_rad: tuple[float, ...]
    velocity_rad_s: tuple[float, ...]
    acceleration_rad_s2: tuple[float, ...]
    model_version: str
    source: str

    def __post_init__(self):
        names = _names(self.joint_names)
        object.__setattr__(self, 'joint_names', names)
        for field in ('lower_rad', 'upper_rad', 'velocity_rad_s', 'acceleration_rad_s2'):
            value = _vector(getattr(self, field), len(names), field)
            object.__setattr__(self, field, tuple(value))
        if (np.any(np.array(self.lower_rad) >= self.upper_rad)
                or min(self.velocity_rad_s) <= 0 or min(self.acceleration_rad_s2) <= 0
                or not self.model_version or self.source not in ('synthetic', 'recorded', 'real')):
            raise ValueError('explicit ordered limits, positive rates and model provenance required')


def build_offline_trajectory(waypoints_rad, limits, *, scene_version, calibration_version,
                             clock_domain, epoch, state_stamp_s, now_s, max_age_s,
                             start_tolerance_rad, expected_start_rad):
    """Build conservative smooth segments, stopping at every waypoint.

    Analytical maxima for s(u)=10u^3-15u^4+6u^5:
    max s'=15/8; max |s''|=10 sqrt(3)/3. Position is monotone.
    The expected start is compared to caller supplied fresh state only; this
    function cannot establish hardware truth or validate its clock mapping.
    """
    if limits is None:
        raise ValueError('unknown limits')
    if not all(isinstance(v, str) and v.strip() for v in
               (scene_version, calibration_version, clock_domain, epoch)):
        raise ValueError('scene/calibration/clock/epoch required')
    scalars = (state_stamp_s, now_s, max_age_s, start_tolerance_rad)
    if not all(isinstance(x, (int, float)) and math.isfinite(x) and x >= 0 for x in scalars):
        raise ValueError('nonnegative finite time/tolerances required')
    if state_stamp_s > now_s or now_s-state_stamp_s > max_age_s:
        raise ValueError('future or stale state')
    q = np.asarray(waypoints_rad, dtype=float)
    n = len(limits.joint_names)
    if q.ndim != 2 or q.shape[1] != n or len(q) < 2 or not np.isfinite(q).all():
        raise ValueError('two or more finite named-joint waypoints required')
    start = _vector(expected_start_rad, n, 'expected_start_rad')
    if np.any(np.abs(q[0]-start) > start_tolerance_rad):
        raise ValueError('trajectory start mismatch')
    if np.any(q < limits.lower_rad) or np.any(q > limits.upper_rad):
        raise ValueError('joint position limit')
    times = [0.0]
    segments = []
    for a, b in zip(q, q[1:]):
        delta = np.abs(b-a)
        duration = max(float(np.max(1.875*delta/limits.velocity_rad_s)),
                       float(np.max(np.sqrt((10*math.sqrt(3)/3)*delta/limits.acceleration_rad_s2))))
        if duration == 0:
            continue
        # Slight margin avoids floating point equality at analytical bounds.
        duration *= 1.001
        segments.append({'start_rad': a.tolist(), 'end_rad': b.tolist(),
                         'start_s': times[-1], 'duration_s': duration})
        times.append(times[-1]+duration)
    if not segments:
        raise ValueError('stationary request has no motion trajectory')
    return {'schema_version': 'c-trajectory-1', 'source': 'offline',
            'joint_names': list(limits.joint_names), 'segments': segments,
            'interpolation': 'quintic_stop_at_each_waypoint',
            'expected_start_rad': start.tolist(), 'model_version': limits.model_version,
            'limits_source': limits.source, 'scene_version': scene_version,
            'calibration_version': calibration_version, 'clock_domain': clock_domain,
            'epoch': epoch, 'state_stamp_s': state_stamp_s,
            'ik': 'NOT_CHECKED', 'trajectory_limits': 'PASS',
            'full_collision': 'UNKNOWN', 'motion_enabled': False}


def sample_segment(segment, time_from_segment_start_s):
    """Evaluate q/dq/ddq; adapters must preserve this interpolation."""
    duration = segment['duration_s']
    t = time_from_segment_start_s
    if not math.isfinite(duration) or duration <= 0 or not math.isfinite(t) or not 0 <= t <= duration:
        raise ValueError('sample time outside positive segment')
    u = t/duration
    a = np.asarray(segment['start_rad'], float)
    delta = np.asarray(segment['end_rad'], float)-a
    return (a+delta*(10*u**3-15*u**4+6*u**5),
            delta*(30*u**2-60*u**3+30*u**4)/duration,
            delta*(60*u-180*u**2+120*u**3)/duration**2)
