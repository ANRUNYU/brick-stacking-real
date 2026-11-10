"""Analyze Orbbec clock_observation rows into a provisional exposure→host bound."""
from __future__ import annotations

import json
import math
import statistics
from pathlib import Path

from brick_stacking.vision.observation_exchange import EXPOSURE_REFERENCE_GLOBAL_MONOTONIC

SCHEMA = "v-clock-error-bound-study-0.1"
ACCEPTED_FOR_OBSERVATION_TIMING = {
    "ACCEPTED_FOR_OBSERVATION_TIMING",
    "PROVISIONAL_MULTI_SESSION_DIAGNOSTIC",
}
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CLOCK_BOUND_EVIDENCE = (
    "docs/team/B/evidence/field_20261110/clock_error_bound_study_v0.1.json"
)


def resolve_clock_bound_evidence_path(path: Path | str | None = None) -> Path | None:
    """Resolve study path against cwd, then repo root. Missing → None (never invent)."""
    raw = Path(path or DEFAULT_CLOCK_BOUND_EVIDENCE)
    candidates = [raw]
    if not raw.is_absolute():
        candidates.append(REPO_ROOT / raw)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def load_observation_timing_bound(path: Path | str | None = None):
    """Return (bound_s, evidence_ref) when a study may fill ObservationBundle timing.

    Does not authorize control_ready or motion. Relative paths try cwd then repo root
    so SSH/capture scripts that do not chdir into the checkout still find the study.
    """
    resolved = resolve_clock_bound_evidence_path(path)
    if resolved is None:
        return None
    report = json.loads(resolved.read_text(encoding="utf-8"))
    bound = report.get("clock_error_bound_s")
    acceptance = report.get("acceptance")
    if bound is None or bound < 0 or acceptance not in ACCEPTED_FOR_OBSERVATION_TIMING:
        return None
    ref = resolved.as_posix()
    for base in (Path.cwd().resolve(), REPO_ROOT.resolve()):
        try:
            ref = resolved.resolve().relative_to(base).as_posix()
            break
        except ValueError:
            continue
    return float(bound), ref


def attach_accepted_timing_bound(bundle: dict, path: Path | str | None = None) -> bool:
    """Fill null clock bound/evidence on a bundle that already has exposure mapping.

    Requires exposure_host_stamp_s. Optionally checks host_boot_epoch against the study.
    Never invents output_monotonic_s. Does not raise control_ready.
    """
    loaded = load_observation_timing_bound(path)
    if loaded is None:
        return False
    bound, ref = loaded
    timing = bundle.setdefault("timing", {})
    exposure = timing.get("exposure_host_stamp_s")
    if exposure is None:
        return False
    if timing.get("clock_error_bound_s") is not None or timing.get("error_bound_evidence_ref"):
        return (
            timing.get("clock_error_bound_s") == bound
            and timing.get("error_bound_evidence_ref") == ref
            and timing.get("validity") == "VALID"
        )
    study_path = resolve_clock_bound_evidence_path(path)
    study = json.loads(study_path.read_text(encoding="utf-8")) if study_path else {}
    epochs = study.get("host_boot_epochs") or []
    boot = timing.get("host_boot_epoch")
    if epochs and boot is not None and boot not in epochs:
        return False
    timing["clock_error_bound_s"] = bound
    timing["error_bound_evidence_ref"] = ref
    timing["validity"] = "VALID"
    timing["reason"] = None
    bundle["control_ready"] = False
    return True


def _pct(values, q):
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    pos = (len(ordered) - 1) * q / 100.0
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return float(ordered[lo])
    return float(ordered[lo] * (hi - pos) + ordered[hi] * (pos - lo))


def load_clock_rows(path: Path):
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    payload = json.loads(text)
    if isinstance(payload, list):
        return payload
    if "frames" in payload:
        return payload["frames"]
    raise ValueError(f"unsupported evidence shape: {path}")


def _extract(row):
    timing = row.get("timing") or row
    clocks = timing.get("sdk_clock_observation") or row.get("clock_observation")
    if not clocks:
        return None
    color = clocks["frames"]["color"]
    exposure = color.get("global_host_monotonic_candidate_s")
    receive = timing.get("host_receive_stamp_s", row.get("host_receive_stamp_s"))
    if exposure is None or receive is None or not color.get("global_available"):
        return None
    return {
        "exposure_host_candidate_s": float(exposure),
        "host_receive_stamp_s": float(receive),
        "receive_minus_exposure_s": float(receive) - float(exposure),
        "sdk_receive_minus_global_s": color.get("sdk_receive_minus_global_s"),
        "bridge_bracket_s": clocks.get("bridge_bracket_s"),
        "rgb_depth_delta_s": timing.get("rgb_depth_delta_s"),
        "output_monotonic_s": timing.get("output_monotonic_s"),
        "sdk_host_clock_type": clocks.get("sdk_host_clock_type"),
        "host_boot_epoch": timing.get("host_boot_epoch"),
    }


def analyze_clock_rows(rows, *, source, half_exposure_s, safety_factor, min_frames):
    samples = [item for item in (_extract(row) for row in rows) if item is not None]
    if len(samples) < min_frames:
        return {
            "schema_version": SCHEMA,
            "status": "INSUFFICIENT_SAMPLES",
            "source": source,
            "n_rows": len(rows),
            "n_usable": len(samples),
            "min_frames": min_frames,
            "control_ready": False,
            "clock_error_bound_s": None,
            "exposure_reference": EXPOSURE_REFERENCE_GLOBAL_MONOTONIC,
        }

    lags = [s["receive_minus_exposure_s"] for s in samples]
    med = statistics.median(lags)
    abs_dev = [abs(v - med) for v in lags]
    bridges = [s["bridge_bracket_s"] for s in samples if s["bridge_bracket_s"] is not None]
    rgb_depth = [s["rgb_depth_delta_s"] for s in samples if s["rgb_depth_delta_s"] is not None]
    sdk_lags = [s["sdk_receive_minus_global_s"] for s in samples
                if s["sdk_receive_minus_global_s"] is not None]
    exp_out = [
        s["output_monotonic_s"] - s["exposure_host_candidate_s"]
        for s in samples if s["output_monotonic_s"] is not None
    ]

    mapping_jitter_s = max(abs_dev) if abs_dev else None
    components = {
        "half_bridge_bracket_s": max(bridges) / 2 if bridges else 0.0,
        "half_rgb_depth_delta_s": max(rgb_depth) / 2 if rgb_depth else 0.0,
        "half_fixed_color_exposure_s": half_exposure_s,
        "mapping_jitter_vs_host_receive_s": mapping_jitter_s,
    }
    raw_bound = sum(components.values())
    bound = raw_bound * safety_factor

    status = "PROVISIONAL_MAPPING_BOUND"
    notes = [
        "exposure_host candidate = SDK color global → process_monotonic sandwich",
        "bound covers bridge, RGB-D pair skew, half exposure, and lag jitter vs host receive",
        "does not optically prove photon-arrival epoch; control_ready stays false",
    ]
    if any(v < 0 for v in lags):
        status = "REJECTED_NEGATIVE_LAG"
        bound = None
        notes.append("host_receive earlier than exposure candidate; mapping rejected")
    elif mapping_jitter_s is not None and mapping_jitter_s > 0.05:
        status = "REJECTED_UNSTABLE_MAPPING"
        bound = None
        notes.append("mapping jitter vs host receive > 50 ms; need longer/cleaner capture")

    return {
        "schema_version": SCHEMA,
        "status": status,
        "source": source,
        "control_ready": False,
        "exposure_reference": EXPOSURE_REFERENCE_GLOBAL_MONOTONIC,
        "n_rows": len(rows),
        "n_usable": len(samples),
        "host_boot_epochs": sorted({s["host_boot_epoch"] for s in samples if s["host_boot_epoch"]}),
        "sdk_host_clock_types": sorted({s["sdk_host_clock_type"] for s in samples if s["sdk_host_clock_type"]}),
        "receive_minus_exposure_s": {
            "p50": _pct(lags, 50),
            "p95": _pct(lags, 95),
            "max": max(lags),
            "min": min(lags),
            "max_abs_dev_from_median": mapping_jitter_s,
        },
        "sdk_receive_minus_global_s": {
            "p50": _pct(sdk_lags, 50),
            "max": max(sdk_lags) if sdk_lags else None,
            "min": min(sdk_lags) if sdk_lags else None,
        },
        "exposure_candidate_to_output_s": {
            "p50": _pct(exp_out, 50),
            "p95": _pct(exp_out, 95),
            "max": max(exp_out) if exp_out else None,
        } if exp_out else None,
        "components_s": components,
        "safety_factor": safety_factor,
        "clock_error_bound_s": bound,
        "notes": notes,
    }
