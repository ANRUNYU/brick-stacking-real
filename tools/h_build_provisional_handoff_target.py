"""Build provisional mid-handoff wrist-target from teach samples (hang/preshape/close/handoff)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from brick_stacking.wrist_handoff.freeze_from_teach import (
    freeze_provisional_handoff_wrist_target_from_teach,
)
from brick_stacking.wrist_handoff.wrist_target import canonical_sha256


def main() -> None:
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("samples", nargs="+", type=Path, help="teach sample JSON paths")
    p.add_argument("output", type=Path, help="wrist-target JSON output")
    p.add_argument("--pack-version", required=True)
    p.add_argument("--hand-pack-output", type=Path, default=None)
    p.add_argument("--table-board-hash", default=None)
    args = p.parse_args()

    samples = [json.loads(path.read_text(encoding="utf-8-sig")) for path in args.samples]
    out = freeze_provisional_handoff_wrist_target_from_teach(
        samples=samples,
        pack_version=args.pack_version,
        table_board_hash=args.table_board_hash,
        notes=[f"source={path.as_posix()}" for path in args.samples],
    )
    pack = out.pop("hand_preset_pack")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    hand_out = args.hand_pack_output
    if hand_out is None:
        hand_out = args.output.with_name(args.output.stem.replace("wrist_target", "hand_preset_pack") + ".json")
        if hand_out == args.output:
            hand_out = args.output.with_name(args.output.stem + "_hand_preset_pack.json")
    hand_out.parent.mkdir(parents=True, exist_ok=True)
    hand_out.write_text(json.dumps(pack, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(args.output)
    print(hand_out)
    print("canonical_sha256", canonical_sha256(out))
    print("targets", [t["name"] for t in out["targets"]])


if __name__ == "__main__":
    main()
