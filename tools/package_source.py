"""Create a portable source ZIP. Never copies Windows venv, SDK or recordings."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED


ROOT_FILES = {"README.md", "CHANGELOG.md", "pyproject.toml", ".gitignore",
              "BRICK_STACKING_REAL_ROBOT_DESIGN_v0.2.md", "PROJECT_STRUCTURE_AND_NAMING.md"}
SOURCE_DIRS = {"src", "tests", "config", "docs", "experiments", "tools", ".github"}
SUFFIXES = {".py", ".md", ".yaml", ".yml", ".json", ".toml"}


def package_source(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    if not (root / "pyproject.toml").is_file():
        raise ValueError("not the independent project root")
    files = []
    candidates = [root / name for name in ROOT_FILES if (root / name).is_file()]
    for name in sorted(SOURCE_DIRS):
        directory = root / name
        if directory.is_dir() and not directory.is_symlink():
            candidates.extend(directory.rglob("*"))
    for path in sorted(candidates):
        relative = path.relative_to(root)
        if path.is_symlink() or not path.is_file() or "__pycache__" in relative.parts:
            continue
        if path == output or not (len(relative.parts) == 1 and path.name in ROOT_FILES
                or relative.parts[0] in SOURCE_DIRS and path.suffix in SUFFIXES):
            continue
        if path.stat().st_size > 2_000_000:
            raise ValueError(f"oversized source file: {relative}")
        files.append((path, relative.as_posix()))
    if output.exists():
        raise FileExistsError("source package exists; choose a new output path")
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {"schema_version": 1, "hardware_enabled": False, "files": {}}
    with ZipFile(output, "x", ZIP_DEFLATED) as archive:
        for path, relative in files:
            content = path.read_bytes()
            archive.writestr(relative, content)
            manifest["files"][relative] = sha256(content).hexdigest()
        archive.writestr("source_manifest.json", json.dumps(manifest, indent=2))
    return {"output": str(output), "file_count": len(files),
            "sha256": sha256(output.read_bytes()).hexdigest()}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    print(json.dumps(package_source(Path(__file__).resolve().parents[1], args.output), indent=2))


if __name__ == "__main__":
    main()
