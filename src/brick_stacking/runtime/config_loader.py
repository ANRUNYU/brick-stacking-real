from pathlib import Path
import yaml


def load_config(path):
    value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("unsupported config schema")
    project = value.get("project", {})
    if project.get("dry_run") is not True or project.get("environment") != "offline":
        raise ValueError("this release supports offline dry_run only")
    mode = value.get("operation", {})
    if mode.get("mode") not in {"DEVELOPMENT_TEST", "AUTONOMY_TRIAL", "COMPETITION_AUTONOMOUS"}:
        raise ValueError("unknown operation mode")
    if not isinstance(mode.get("manual_intervention_allowed"), bool):
        raise ValueError("manual intervention policy must be explicit")
    if mode["mode"] in {"AUTONOMY_TRIAL", "COMPETITION_AUTONOMOUS"} and mode["manual_intervention_allowed"]:
        raise ValueError("autonomous mode prohibits manual recovery")
    return value
