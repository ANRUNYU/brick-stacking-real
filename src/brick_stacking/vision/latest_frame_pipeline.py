"""One pending RGB-D pair and one current observation, scoped to a stream session."""
from collections import Counter, deque
from copy import deepcopy
import math
from threading import Lock
import time

import numpy as np

from brick_stacking.vision.observation_exchange import observation_exchange


class LatestFramePipeline:
    def __init__(self, detector, *, nominal_edge_m, max_receive_age_s, max_pair_skew_s,
                 clock=time.monotonic, metrics_window=256, monitor=None):
        if not all(math.isfinite(value) and value > 0 for value in
                   (max_receive_age_s, max_pair_skew_s)):
            raise ValueError("explicit positive age and pairing limits required")
        if type(metrics_window) is not int or metrics_window < 1:
            raise ValueError("positive metrics window required")
        self._detector = detector
        self._monitor = monitor
        self._nominal_edge_m = nominal_edge_m
        self._max_age_s = max_receive_age_s
        self._max_skew_s = max_pair_skew_s
        self._clock = clock
        self._lock = Lock()
        self._consumer = Lock()
        self._session = None
        self._seen_epochs = set()
        self._pending = None
        self._latest = None
        self._last_stamps = (-1., -1.)
        self._generation = 0
        self._counts = Counter()
        self._measurements = deque(maxlen=metrics_window)

    def start_session(self, *, camera_id, epoch, profile, profile_hash):
        with self._lock:
            if not all((camera_id, epoch, profile, profile_hash)) or epoch in self._seen_epochs:
                raise ValueError("fresh capture epoch and explicit camera/profile required")
            self._invalidate()
            self._session = (camera_id, epoch, profile, profile_hash)
            self._seen_epochs.add(epoch)
            self._last_stamps = (-1., -1.)
            self._counts["sessions"] += 1

    def invalidate(self):
        """Clear pending, in-flight and published data after disconnect or scene change."""
        with self._lock:
            self._invalidate()

    def _invalidate(self):
        if self._pending is not None:
            self._counts["invalidated_pending"] += 1
        self._generation += 1
        self._session = self._pending = self._latest = None

    def _fresh(self, context, now):
        stamp = context.host_receive_s
        return stamp is not None and 0 <= now - stamp <= self._max_age_s

    def offer(self, frame, context):
        """Accept a complete pair stamped by this process's monotonic clock."""
        with self._lock:
            key = (frame.camera_id, context.epoch, context.profile, context.profile_hash)
            if key != self._session:
                self._counts["wrong_session_or_profile"] += 1
                return False
            if (context.host_clock_domain != "process_monotonic"
                    or not self._fresh(context, self._clock())):
                self._counts["stale_or_unknown_arrival"] += 1
                return False
            delta = context.rgb_depth_delta_s
            if delta is None or delta > self._max_skew_s or context.color_device_s != frame.stamp_s:
                self._counts["invalid_pair_timing"] += 1
                return False
            stamps = (context.color_device_s, context.depth_device_s)
            if any(stamp <= previous for stamp, previous in zip(stamps, self._last_stamps)):
                self._counts["repeated_or_reversed_stamp"] += 1
                self._invalidate()
                return False
            self._last_stamps = stamps
            if self._pending is not None:
                self._counts["overwritten_pending"] += 1
            self._pending = (frame, context, self._clock())
            self._counts["accepted"] += 1
            return True

    def process_latest(self, *, save=None):
        """Run one detection outside the producer lock. Save must preserve this exact pair."""
        if not self._consumer.acquire(blocking=False):
            return None
        try:
            with self._lock:
                pending, self._pending = self._pending, None
                generation = self._generation
                if pending is None:
                    return None
                frame, context, paired = pending
                started = self._clock()
                if not self._fresh(context, started):
                    self._counts["expired_before_detection"] += 1
                    return None
            try:
                reason = None
                try:
                    detections = self._detector.detect(frame)
                except ValueError as exc:
                    detections, reason = (), f"tabletop_detection_unavailable: {exc}"
                detected = self._clock()
                temporal = None
                if self._monitor is not None:
                    temporal = (self._monitor.invalidate(reason) if reason
                                else self._monitor.update(frame, detections))
                bundle = observation_exchange(
                    frame, context, detections, nominal_edge_m=self._nominal_edge_m,
                    unavailable_reason=reason,
                )
                with self._lock:
                    if generation != self._generation:
                        self._counts["invalidated_during_detection"] += 1
                        return None
                    if not self._fresh(context, self._clock()):
                        self._counts["expired_after_detection"] += 1
                        return None
                    if temporal is not None and not temporal["scene_consistent"]:
                        self._latest = None
                if temporal is not None:
                    bundle["timing"]["scene_consistency"] = temporal
                if save is not None:
                    save(frame, context)
            except Exception:
                with self._lock:
                    self._counts["processing_errors"] += 1
                    if generation == self._generation:
                        self._latest = None
                raise
            with self._lock:
                output = self._clock()
                if generation != self._generation:
                    self._counts["invalidated_during_detection"] += 1
                    return None
                if not self._fresh(context, output):
                    self._counts["expired_before_output"] += 1
                    return None
                bundle["timing"].update(
                    pair_ready_monotonic_s=paired, detection_started_monotonic_s=started,
                    detection_finished_monotonic_s=detected, output_monotonic_s=output,
                    receive_to_output_s=output - context.host_receive_s,
                    exposure_to_output_s=None,
                )
                self._latest = (context, bundle)
                self._measurements.append((output - context.host_receive_s, detected - started))
                self._counts["published"] += 1
                if reason:
                    self._counts["detection_unavailable"] += 1
                return deepcopy(bundle)
        finally:
            self._consumer.release()

    def get_observation(self):
        with self._lock:
            if self._latest is None or not self._fresh(self._latest[0], self._clock()):
                return None
            return deepcopy(self._latest[1])

    def metrics(self):
        with self._lock:
            rows, counts = tuple(self._measurements), dict(self._counts)
        metrics = dict(counts=counts, latency_samples=len(rows), exposure_to_output_s=None)
        for index, name in enumerate(("receive_to_output_s", "detection_s")):
            values = [row[index] for row in rows]
            metrics[name] = dict(zip(("p50", "p95", "max"),
                                     map(float, np.percentile(values, [50, 95, 100])))) if values else None
        return metrics
