"""Collision-safe minute-resolution experiment IDs and auditable offline output."""
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from pathlib import Path
import json
import re
import platform
import yaml


class RunRecorder:
    def __init__(self, root, objective, object_name, interface_code, config, *, now=None, source_commit=None):
        if not all(re.fullmatch(r"[A-Z][A-Za-z0-9]*", s) for s in (objective, object_name)):
            raise ValueError("objective/object must be PascalCase tokens")
        if interface_code not in {"RGBD", "TF2", "MOCK", "PYTHON"}:
            raise ValueError("undefined interface code; ID is not approved")
        now = now or datetime.now(timezone(timedelta(hours=8)))
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("timezone-aware timestamp required")
        base = Path(root) / now.strftime("%Y-%m-%d")
        base.mkdir(parents=True, exist_ok=True)
        stem = f"{objective}_{object_name}_{interface_code}_{now:%Y%m%d%H%M}"
        for index in range(1, 10000):
            path = base / (stem if index == 1 else f"{stem}_R{index:02d}")
            try:
                path.mkdir()
                break
            except FileExistsError:
                continue
        else:
            raise RuntimeError("run ID capacity exhausted")
        self.path = path
        snapshot = yaml.safe_dump(config, allow_unicode=True, sort_keys=True)
        (path / "config_snapshot.yaml").write_text(snapshot, encoding="utf-8")
        self.manifest = dict(run_id=path.name, objective=objective, object=object_name,
            interface_code=interface_code, started_at=now.isoformat(),
            mode=config["operation"]["mode"], hardware_enabled=False,
            operator="offline_automation", source_commit=source_commit,
            config_hash=sha256(snapshot.encode()).hexdigest(), calibration_id=None,
            hardware_inventory_id="inventory_20261105_draft", sdk_versions={},
            result="INCONCLUSIVE", manual_intervention_count=0,
            notes="Offline software evidence only; no device controlled.")
        digest = sha256()
        package_root = Path(__file__).resolve().parents[1]
        for source_path in sorted(package_root.rglob("*.py")):
            digest.update(source_path.relative_to(package_root).as_posix().encode())
            digest.update(source_path.read_bytes())
        self.manifest["source_tree_sha256"] = digest.hexdigest()
        self.manifest["python_version"] = platform.python_version()
        self._write_manifest()
        (path / "events.jsonl").touch()

    def _write_manifest(self):
        (self.path / "manifest.yaml").write_text(yaml.safe_dump(self.manifest, allow_unicode=True), encoding="utf-8")

    def event(self, kind, data):
        with (self.path / "events.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"kind": kind, "data": data}, ensure_ascii=False, allow_nan=False) + "\n")

    def finish(self, result, metrics, explanation):
        if result not in {"PASS", "FAIL", "INCONCLUSIVE", "SKIPPED", "ABORTED"}:
            raise ValueError("invalid result")
        self.manifest["result"] = result
        self._write_manifest()
        (self.path / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        (self.path / "result.md").write_text(f"# {result}\n\n{explanation}\n\nNo physical hardware execution.\n", encoding="utf-8")
