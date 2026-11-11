import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
from replay_single_block_handoff import bind_and_replay
from brick_stacking.execution.single_block_mock_replay import run_single_block_mock_replay

FIELD = ROOT / "docs/team/B/evidence/field_20261110/_chain_test_20261111"


def replay(change=None):
    readiness, shadow = (json.loads((FIELD / name).read_text(encoding="utf-8"))
                         for name in ("live_pre_grasp_readiness.json", "live_shadow_plan_bundle.json"))
    if change:
        change(shadow)
    return bind_and_replay(readiness, shadow, ROOT / "config/planning/single_block_approach.yaml",
                           ROOT / "config/planning/single_block_joint_limits_synthetic.yaml")


def test_field_context_reaches_only_mock():
    report = replay()
    assert report["status"] == "MOCK_DONE", report["reason"]
    assert report["permit"] is None and report["control_ready"] is False
    assert report["plan"]["poses"]["frame"] == "synthetic_tabletop"
    assert report["plan"]["trajectory_hash"] != report["shadow_hash"]
    plan = report["plan"]
    assert run_single_block_mock_replay(plan, frame_id="L_arm_root").stage.value == "SAFE_HALT"
    plan["trajectory"]["points"][-1]["q_rad"][0] += 0.01
    assert "hash mismatch" in run_single_block_mock_replay(plan).reason


@pytest.mark.parametrize("change", [
    lambda s: s["identity"].update(observation_id="unrelated"),
    lambda s: s["identity"].update(calibration_hash="other"),
    lambda s: s["trajectory"]["points"][0]["q_rad"].__setitem__(0, 0.1),
    lambda s: s.update(motion_enabled=True),
])
def test_reject_mixed_or_changed_handoff(change):
    assert replay(change)["status"] == "BLOCKED"
