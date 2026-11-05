"""Offline-only fail-closed gate. NOT a real robot safety implementation."""
import math


class OfflineSafetyGate:
    def __init__(self, *, max_age_s):
        if not math.isfinite(max_age_s) or max_age_s <= 0:
            raise ValueError("positive observation age required")
        self.max_age_s = max_age_s

    def check(self, config, port, scene, *, now_s, clock_domain, epoch):
        if config["project"] != {"dry_run": True, "environment": "offline"}:
            raise ValueError("offline dry_run configuration required")
        if getattr(port, "backend", None) != "mock" or getattr(port, "hardware_enabled", None) is not False:
            raise ValueError("real/device adapters are not accepted by offline executor")
        if scene.source != "synthetic" or scene.epoch != epoch or scene.clock_domain != clock_domain:
            raise ValueError("mock source/epoch/clock mismatch")
        age = now_s - scene.stamp_s
        if not math.isfinite(age) or not 0 <= age <= self.max_age_s:
            raise ValueError("stale/future observation")
        operation = config["operation"]
        if operation["mode"] in {"AUTONOMY_TRIAL", "COMPETITION_AUTONOMOUS"} and operation["manual_intervention_allowed"]:
            raise ValueError("autonomous workflow cannot depend on manual recovery")
