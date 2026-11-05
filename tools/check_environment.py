"""Standard-library-only, read-only deployment inventory; no SDK imports."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import sys


def inspect_environment(*, require_linux_jazzy=False):
    system = platform.system()
    issues = []
    os_release = {}
    if system == "Linux" and Path("/etc/os-release").exists():
        for line in Path("/etc/os-release").read_text().splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                os_release[key] = value.strip('"')
    dependencies = {name: importlib.util.find_spec(name) is not None
                    for name in ("numpy", "cv2", "yaml", "pytest", "rclpy")}
    if sys.version_info < (3, 11):
        issues.append("Python >=3.11 required")
    for name in ("numpy", "cv2", "yaml"):
        if not dependencies[name]:
            issues.append(f"missing offline dependency: {name}")
    if require_linux_jazzy:
        if system != "Linux" or os_release.get("ID") != "ubuntu" or os_release.get("VERSION_ID") != "24.04":
            issues.append("requires Ubuntu 24.04")
        if os.environ.get("ROS_DISTRO") != "jazzy" or not dependencies["rclpy"]:
            issues.append("Jazzy environment not sourced or rclpy unavailable to selected Python")
    return {"os": system, "os_release": os_release, "architecture": platform.machine(),
        "python": sys.version, "python_executable": sys.executable, "dependencies": dependencies,
        "ros_distro": os.environ.get("ROS_DISTRO"), "issues": issues,
        "software_environment_check_passed": not issues, "sdk_instantiated": False,
        "hardware_tested": False, "motion_ready": False,
        "notice": "Import discoverability only; not device, ABI, ROS graph or calibration acceptance."}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--require-linux-jazzy", action="store_true")
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    report = inspect_environment(require_linux_jazzy=args.require_linux_jazzy)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)
    return 0 if not report["issues"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
