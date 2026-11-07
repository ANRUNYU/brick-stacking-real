"""Compute descriptive tracking metrics from an already synchronized CSV."""

import argparse
from collections.abc import Iterable
import csv
import json
import math
from pathlib import Path

FIELDS = ("target_stamp_s", "target_rad", "feedback_stamp_s", "actual_rad")


def summarize_tracking(
    rows: Iterable[tuple[float, float, float, float]], *, max_skew_s: float, max_gap_s: float,
) -> dict[str, float | int]:
    """Reject incomplete or misaligned traces before reporting observed values."""
    if not math.isfinite(max_skew_s) or max_skew_s < 0:
        raise ValueError("max_skew_s must be finite and nonnegative")
    if not math.isfinite(max_gap_s) or max_gap_s <= 0:
        raise ValueError("max_gap_s must be finite and positive")

    errors = []
    peak_target_speed = peak_actual_speed = peak_skew = 0.0
    first_stamp = None
    previous = None
    for index, row in enumerate(rows, start=1):
        target_stamp, target, feedback_stamp, actual = row
        if not all(map(math.isfinite, row)):
            raise ValueError(f"sample {index}: non-finite timestamp or position")
        skew = abs(target_stamp - feedback_stamp)
        if skew > max_skew_s:
            raise ValueError(f"sample {index}: target and feedback exceed maximum skew")
        peak_skew = max(peak_skew, skew)
        error = abs(target - actual)
        if not math.isfinite(error):
            raise ValueError(f"sample {index}: position error overflow")
        errors.append(error)

        if previous is None:
            first_stamp = feedback_stamp
        else:
            prior_target_stamp, prior_target, prior_feedback_stamp, prior_actual = previous
            target_gap = target_stamp - prior_target_stamp
            feedback_gap = feedback_stamp - prior_feedback_stamp
            if not (0 < target_gap <= max_gap_s and 0 < feedback_gap <= max_gap_s):
                raise ValueError(f"sample {index}: timestamps are non-increasing or exceed maximum gap")
            target_speed = abs(target - prior_target) / target_gap
            actual_speed = abs(actual - prior_actual) / feedback_gap
            if not (math.isfinite(target_speed) and math.isfinite(actual_speed)):
                raise ValueError(f"sample {index}: position rate overflow")
            peak_target_speed = max(peak_target_speed, target_speed)
            peak_actual_speed = max(peak_actual_speed, actual_speed)
        previous = row

    if len(errors) < 2:
        raise ValueError("at least two tracking samples are required")
    duration = feedback_stamp - first_stamp
    if not math.isfinite(duration):
        raise ValueError("feedback duration overflow")
    errors.sort()
    return {
        "sample_count": len(errors),
        "feedback_duration_s": duration,
        "max_skew_s": peak_skew,
        "p95_abs_error_rad": errors[math.ceil(0.95 * len(errors)) - 1],
        "max_abs_error_rad": errors[-1],
        "final_abs_error_rad": error,
        "peak_sampled_target_speed_rad_s": peak_target_speed,
        "peak_sampled_feedback_speed_rad_s": peak_actual_speed,
    }


def _csv_samples(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        if tuple(next(reader, ())) != FIELDS:
            raise ValueError(f"expected CSV columns: {', '.join(FIELDS)}")
        for line, row in enumerate(reader, start=2):
            try:
                if len(row) != len(FIELDS):
                    raise ValueError("wrong column count")
                target_stamp, target, feedback_stamp, actual = map(float, row)
            except ValueError as exc:
                raise ValueError(f"CSV row {line}: expected four numeric fields") from exc
            yield target_stamp, target, feedback_stamp, actual


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--max-skew-s", type=float, required=True)
    parser.add_argument("--max-gap-s", type=float, required=True)
    args = parser.parse_args()
    try:
        metrics = summarize_tracking(
            _csv_samples(args.csv_path), max_skew_s=args.max_skew_s, max_gap_s=args.max_gap_s,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(metrics, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
