"""CLI for provisional exposure→host clock bound study (#7)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tools")]

from brick_stacking.vision.clock_error_bound import analyze_clock_rows, load_clock_rows  # noqa: E402


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("evidence", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--half-exposure-s", type=float, default=50e-6)
    p.add_argument("--safety-factor", type=float, default=2.0)
    p.add_argument("--min-frames", type=int, default=12)
    args = p.parse_args(argv)
    report = analyze_clock_rows(
        load_clock_rows(args.evidence),
        source=str(args.evidence).replace("\\", "/"),
        half_exposure_s=args.half_exposure_s,
        safety_factor=args.safety_factor,
        min_frames=args.min_frames,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "n_usable": report["n_usable"],
        "clock_error_bound_s": report["clock_error_bound_s"],
        "output": str(args.output).replace("\\", "/"),
    }, indent=2))


if __name__ == "__main__":
    main()
