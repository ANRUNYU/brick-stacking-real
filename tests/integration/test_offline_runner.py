import json
from pathlib import Path
from brick_stacking.app.offline_runner import main


def test_synthetic_and_recording_replay(tmp_path):
    config = str(Path(__file__).resolve().parents[2] / "config/defaults.yaml")
    assert main(["--synthetic", "--config", config, "--output-root", str(tmp_path)]) == 0
    fixture = next(tmp_path.rglob("synthetic_rgbd.npz"))
    assert main(["--recordings", str(fixture), "--config", config, "--output-root", str(tmp_path)]) == 0
    manifests = list(tmp_path.rglob("metrics.json"))
    assert len(manifests) == 2
    assert all(not json.loads(p.read_text(encoding="utf-8"))["hardware_tested"] for p in manifests)


def test_bad_recording_writes_aborted_report(tmp_path):
    config = str(Path(__file__).resolve().parents[2] / "config/defaults.yaml")
    assert main(["--recordings", str(tmp_path / "missing.npz"), "--config", config,
                 "--output-root", str(tmp_path / "runs")]) == 2
    assert "ABORTED" in next((tmp_path / "runs").rglob("result.md")).read_text(encoding="utf-8")
