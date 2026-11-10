"""Write operator policy attest for control_ready elevation (default closed).

Does NOT raise control_ready by itself. Does not open CAN / enable actuators /
issue live Permit. Pass the output JSON to tools/host_control_readiness.py
--operator-policy-attest. Use --attested only for an explicit operator decision.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src")]

from brick_stacking.execution.host_policy_attest import (  # noqa: E402
    build_host_policy_attest,
)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--operator", required=True, help="who makes the policy decision")
    p.add_argument(
        "--evidence-ref",
        required=True,
        help="path/URI to readiness/checklist evidence justifying the decision",
    )
    p.add_argument("--notes", default="")
    p.add_argument(
        "--attested",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="default false (switch closed); --attested opens the policy switch",
    )
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)

    payload = build_host_policy_attest(
        operator=args.operator,
        evidence_ref=str(args.evidence_ref),
        notes=args.notes,
        attested=bool(args.attested),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "schema_version": payload["schema_version"],
                "attested": payload["attested"],
                "control_ready": False,
                "output": str(args.output).replace("\\", "/"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
