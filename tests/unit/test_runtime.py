from datetime import datetime, timezone, timedelta
import json
import yaml
import pytest
from brick_stacking.runtime.config_loader import load_config
from brick_stacking.runtime.run_recorder import RunRecorder
from brick_stacking.hardware.urdf_inspection import inspect_urdf


@pytest.mark.parametrize("change", ["real", "not_dry", "competition_manual", "unknown_mode"])
def test_unsafe_or_unknown_configuration_rejected(config, tmp_path, change):
    if change == "real": config["project"]["environment"] = "real"
    if change == "not_dry": config["project"]["dry_run"] = False
    if change == "competition_manual": config["operation"]["mode"] = "COMPETITION_AUTONOMOUS"
    if change == "unknown_mode": config["operation"]["mode"] = "UNKNOWN"
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError): load_config(p)


def test_run_name_collision_and_manifest(config, tmp_path):
    now = datetime(2026, 11, 5, 14, 1, tzinfo=timezone(timedelta(hours=8)))
    a = RunRecorder(tmp_path, "Perception", "AdjacentBlocks", "RGBD", config, now=now)
    b = RunRecorder(tmp_path, "Perception", "AdjacentBlocks", "RGBD", config, now=now)
    assert a.path.name == "Perception_AdjacentBlocks_RGBD_202611051401"
    assert b.path.name.endswith("_R02")
    a.event("observation", {"hardware": False})
    a.finish("PASS", {"offline_only": True}, "fixture checked")
    manifest = yaml.safe_load((a.path / "manifest.yaml").read_text())
    assert manifest["started_at"].endswith("+08:00") and not manifest["hardware_enabled"]
    assert json.loads((a.path / "metrics.json").read_text())["offline_only"]
    with pytest.raises(ValueError):
        RunRecorder(tmp_path, "Mobility", "IndexFinger", "ID", config)


def test_urdf_missing_limits_not_invented(tmp_path):
    p = tmp_path / "robot.urdf"
    p.write_text('<robot name="fixture"><link name="a"/><link name="b"/>'
                 '<joint name="j" type="fixed"><parent link="a"/><child link="b"/></joint></robot>')
    result = inspect_urdf(p)
    assert result["joints"][0]["declared_limits"] is None
    assert not result["hardware_match_verified"]
