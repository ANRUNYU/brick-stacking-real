"""Replay paired mainline evidence on the single-block MockArm/MockHand path."""
import argparse
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path

from brick_stacking.arm.adapter import trajectory_hash
from brick_stacking.execution.single_block_mock_replay import run_single_block_mock_replay
from brick_stacking.planning.single_block_plan_bundle import build_single_block_plan_bundle
from brick_stacking.planning.lateral_approach import load_approach_config

ROOT = Path(__file__).resolve().parents[1]


def bind_and_replay(readiness, shadow, approach_path, limits_path):
    report = dict(control_ready=False, motion_enabled=False, permit=None,
                  status="BLOCKED", physical_execution=False)
    try:
        if (readiness["schema_version"] != "pre-grasp-readiness-0.2"
                or shadow["schema_version"] != "m-shadow-plan-bundle-0.1"
                or readiness["vision_pre_grasp_ready"] is not True
                or readiness["evidence_gates_clear"] is not True
                or readiness["phase"] != "pre_grasp"
                or readiness["permit"] is not None
                or any(doc[key] is not False for doc in (readiness, shadow)
                       for key in ("control_ready", "motion_enabled"))
                or shadow["executable"] is not False):
            raise ValueError("expected vision-ready diagnostic handoff")
        diag = readiness["diagnostic_permit"]
        ctx = diag["context_present"]
        identity = shadow["identity"]
        for key in ("target_id", "slot_id", "reference_id", "region_id", "observation_id",
                    "scene_version", "epoch", "clock_domain", "frame_id", "calibration_hash", "config_hash"):
            source = "config_hash_or_profile_hash" if key == "config_hash" else key
            if not isinstance(identity[key], str) or not identity[key] or identity[key] != ctx[source]:
                raise ValueError(f"context mismatch: {key}")
        digest = trajectory_hash(shadow["trajectory"])
        if any(value != digest for value in (
                shadow["trajectory_hash"], shadow["trajectory"]["hash"],
                diag["live_permit_field_status"]["trajectory_hash"]["value"])):
            raise ValueError("shadow trajectory hash mismatch")
        approach = load_approach_config(approach_path)
        for key in ("slot_id", "target_id", "reference_id"):
            if approach[key] != identity[key]:
                raise ValueError(f"template mismatch: {key}")
        config_digest = sha256(json.dumps(
            [sha256(p.read_bytes()).hexdigest() for p in (approach_path, limits_path)]
        ).encode()).hexdigest()
        plan = build_single_block_plan_bundle(
            approach_config=approach, limits_config_path=limits_path,
            world_frame="synthetic_tabletop", observation_id=identity["observation_id"],
            calibration_hash=identity["calibration_hash"], scene_version=identity["scene_version"],
            config_hash=config_digest)
        replay = run_single_block_mock_replay(plan, block_id=identity["target_id"])
        report.update(status="MOCK_DONE" if replay.stage.value == "DONE" else "BLOCKED",
                      reason=replay.reason, observation_context=identity, shadow_hash=digest,
                      plan=plan, replay=asdict(replay))
    except (ValueError, KeyError, TypeError) as exc:
        report["reason"] = str(exc)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("readiness", "shadow", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    load = lambda path: json.loads(path.read_text(encoding="utf-8"))
    report = bind_and_replay(load(args.readiness), load(args.shadow),
                             ROOT / "config/planning/single_block_approach.yaml",
                             ROOT / "config/planning/single_block_joint_limits_synthetic.yaml")
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(report["status"], report.get("reason") or "")
    return 0 if report["status"] == "MOCK_DONE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
