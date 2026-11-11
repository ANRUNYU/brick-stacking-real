"""Offline T2 stage dry-run (no CAN / no motion)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from brick_stacking.execution.t2_touch_lift_package import build_t2_package


def main() -> None:
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--attest-block-present", action="store_true")
    p.add_argument("--attest-clear-workspace", action="store_true")
    p.add_argument("--attest-e-stop", action="store_true")
    args = p.parse_args()
    result = build_t2_package(
        mock=True,
        block_present_attested=bool(args.attest_block_present),
        clear_workspace_attested=bool(args.attest_clear_workspace),
        e_stop_reachable_attested=bool(args.attest_e_stop),
    )
    payload = {
        "stage": result.stage.value,
        "reason": result.reason,
        "stages": result.stages,
        "events": result.events,
        "control_ready": result.control_ready,
        "executable": result.executable,
        "live_motion_allowed": result.live_motion_allowed,
        "payload": result.payload,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(result.stage.value, result.reason)


if __name__ == "__main__":
    main()
