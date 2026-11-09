"""Windows offline tests limited to vision, camera data and localization math."""
from pathlib import Path
import subprocess
import sys
from brick_stacking.runtime.config_loader import load_config
from brick_stacking.runtime.run_recorder import RunRecorder


def main():
    root = Path(__file__).resolve().parents[2]
    recorder = RunRecorder(root / "artifacts/test_runs", "Verification", "VisionCore", "PYTHON",
                           load_config(root / "config/defaults.yaml"))
    command = [sys.executable, "-m", "pytest", "-q", "tests/unit/vision", "tests/unit/localization",
               "tests/unit/test_camera_frame.py", "tests/integration/test_rgbd_to_world_pose.py",
               "-k", "not mock_devices", "--junitxml", str(recorder.path / "junit.xml"),
               "--basetemp", str(recorder.path / "pytest_temp")]
    recorder.event("test_start", {"scope": "vision_only", "command": command})
    try:
        result = subprocess.run(command, cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=120)
        (recorder.path / "pytest_output.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
        recorder.finish("PASS" if result.returncode == 0 else "FAIL",
                        {"exit_code": result.returncode, "camera_opened": False, "robot_control_accessed": False},
                        "Offline vision/math tests; actual camera capture is a separate acceptance stage.")
        print(result.stdout)
        print(recorder.path)
        return result.returncode
    except (OSError, subprocess.TimeoutExpired) as exc:
        recorder.finish("ABORTED", {"robot_control_accessed": False}, str(exc))
        print(exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
