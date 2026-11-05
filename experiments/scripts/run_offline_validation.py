"""Run the offline suite and retain exact command/output in one named record."""
from pathlib import Path
import subprocess
import sys
from brick_stacking.runtime.config_loader import load_config
from brick_stacking.runtime.run_recorder import RunRecorder


def main():
    root = Path(__file__).resolve().parents[2]
    config = load_config(root / "config/defaults.yaml")
    recorder = RunRecorder(root / "artifacts/test_runs", "Verification", "OfflineCore", "PYTHON", config)
    command = [sys.executable, "-m", "pytest", "-q", "--junitxml", str(recorder.path / "junit.xml"),
               "--basetemp", str(recorder.path / "pytest_temp")]
    recorder.event("test_start", {"command": command, "hardware_enabled": False})
    try:
        result = subprocess.run(command, cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=120)
        (recorder.path / "pytest_output.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
        verdict = "PASS" if result.returncode == 0 else "FAIL"
        recorder.finish(verdict, {"pytest_exit_code": result.returncode, "hardware_tested": False},
                        "See junit.xml and pytest_output.txt; offline software tests only.")
        print(result.stdout)
        print(f"{verdict}: {recorder.path}")
        return result.returncode
    except (subprocess.TimeoutExpired, OSError) as exc:
        recorder.finish("ABORTED", {"hardware_tested": False}, str(exc))
        print(f"ABORTED: {exc}; report: {recorder.path}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
