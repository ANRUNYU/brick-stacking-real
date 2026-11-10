"""Operator policy attest prerequisite for future host control_ready elevation.

Default is unattested (switch closed). Never invents live Permit, never opens CAN,
never enables motion, and never auto-opens. Even with attested=true, the host
readiness reporter keeps control_ready=false (large-motion safety); elevation is
deferred to a dedicated host path.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import json

SCHEMA = "host-control-ready-policy-attest-0.1"


@dataclass(frozen=True)
class HostPolicyAttest:
    schema_version: str
    attested: bool
    operator: str | None
    evidence_ref: str | None
    notes: str
    control_ready: bool
    motion_enabled: bool
    path: str | None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        # Hard invariants: the attest record itself never raises enablement.
        payload["control_ready"] = False
        payload["motion_enabled"] = False
        return payload


def empty_attest(*, path: str | None = None) -> HostPolicyAttest:
    return HostPolicyAttest(
        schema_version=SCHEMA,
        attested=False,
        operator=None,
        evidence_ref=None,
        notes="default unattested; control_ready stays false",
        control_ready=False,
        motion_enabled=False,
        path=path,
    )


def load_host_policy_attest(path: str | Path | None) -> HostPolicyAttest:
    """Load attest JSON. Missing path → unattested default."""
    if path is None:
        return empty_attest()
    p = Path(path)
    if not p.is_file():
        return empty_attest(path=str(p).replace("\\", "/"))
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("host policy attest must be a JSON object")
    schema = raw.get("schema_version")
    if schema not in {SCHEMA, None}:
        # Accept only known schema; reject silent upgrades.
        if schema != SCHEMA:
            raise ValueError(f"unsupported host policy attest schema: {schema}")
    attested = bool(raw.get("attested") is True or raw.get("operator_attest_control_ready") is True)
    return HostPolicyAttest(
        schema_version=SCHEMA,
        attested=attested,
        operator=(str(raw["operator"]) if raw.get("operator") else None),
        evidence_ref=(str(raw["evidence_ref"]) if raw.get("evidence_ref") else None),
        notes=str(raw.get("notes") or ""),
        control_ready=False,
        motion_enabled=False,
        path=str(p).replace("\\", "/"),
    )


def build_host_policy_attest(
    *,
    operator: str,
    evidence_ref: str,
    notes: str = "",
    attested: bool = False,
) -> dict[str, Any]:
    """Build a durable attest record. Default attested=False (switch closed)."""
    if attested and not (operator and evidence_ref):
        raise ValueError("attested=true requires operator and evidence_ref")
    return {
        "schema_version": SCHEMA,
        "attested": bool(attested),
        "operator_attest_control_ready": bool(attested),
        "operator": operator,
        "evidence_ref": evidence_ref.replace("\\", "/"),
        "notes": notes,
        "control_ready": False,
        "motion_enabled": False,
        "permit": None,
        "usage": [
            "Pass to tools/host_control_readiness.py --operator-policy-attest",
            "attested=true is a prerequisite only; host_control_readiness still reports control_ready=false",
            "Does not open CAN; does not enable actuators; does not issue live Permit",
            "formal_grasp_entry_allowed remains independently gated (live Permit + live arm)",
            "Default attested=false — never auto-open before V+M merge / dedicated elevation path",
        ],
    }
