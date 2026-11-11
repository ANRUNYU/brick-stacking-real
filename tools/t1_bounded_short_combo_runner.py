#!/usr/bin/env python3
"""T1 bounded short-combo runner (default motion OFF).

Dry-plan path (default):
  emit joint-space out-and-back waypoints; never opens CAN / never moves.

Live path (explicit):
  --enable-live-motion + --authorization-ref + host_monitor base URL
  → READY session → optional J6 ENABLE-only hold → sequential waypoints
    (PREPARE→ENABLE→MOVE→RELEASE) → fail-stop → evidence JSON.

Not a synthetic H3 / PlanBundle live trajectory. control_ready stays false.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brick_stacking.execution.t1_bounded_live_runner import (  # noqa: E402
    MAX_SHORT_COMBO_STEP_DEG,
    build_t1_short_combo_dry_plan,
    default_short_combo_waypoints,
    evaluate_t1_prerequisites,
)

POS_ERR_TOL_RAD = 0.012
DEFAULT_AUTH = "chat-20261111-operator-continue-t1-bounded"


def _http_json(
    base: str,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    timeout: float = 180.0,
) -> dict[str, Any]:
    url = base.rstrip("/") + path
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            http_code = int(resp.status)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        http_code = int(exc.code)
        try:
            payload = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            payload = {"raw": raw[:500]}
        raise RuntimeError(
            f"API error http={http_code} path={path} body={json.dumps(payload, ensure_ascii=False)}"
        ) from exc
    payload = json.loads(raw) if raw.strip() else {}
    if not isinstance(payload, dict):
        raise RuntimeError(f"non-object JSON from {path}: {payload!r}")
    payload = dict(payload)
    payload["_http_code"] = http_code
    if payload.get("ok") is False:
        raise RuntimeError(
            f"API ok=false path={path} body={json.dumps(payload, ensure_ascii=False)}"
        )
    return payload


def _run_waypoint(
    base: str,
    evidence: dict[str, Any],
    waypoint: dict[str, Any],
) -> dict[str, Any]:
    joint = int(waypoint["joint"])
    step_deg = float(waypoint["step_deg"])
    direction = int(waypoint["direction"])
    tag = f"wp{waypoint['index']}_j{joint}_{waypoint.get('phase', 'x')}"
    print(
        f"PREPARE J{joint} step={step_deg} direction={direction} phase={waypoint.get('phase')}"
    )
    prep = _http_json(
        base,
        "POST",
        "/api/control/joint/prepare",
        {"joint": joint, "step_deg": step_deg, "direction": direction},
    )
    evidence["steps"].append({"name": f"{tag}_prepare", "ok": True, "result": prep})
    plan = prep.get("plan") or {}

    print(f"ENABLE J{joint}")
    en = _http_json(
        base,
        "POST",
        "/api/control/joint/enable",
        {"joint": joint, "confirm": "ENABLE"},
        timeout=120.0,
    )
    evidence["steps"].append({"name": f"{tag}_enable", "ok": True, "result": en})
    # ENABLE may re-anchor start/target; prefer latest plan when present.
    plan = (en.get("plan") or plan)

    print(f"MOVE J{joint}")
    mv = _http_json(
        base,
        "POST",
        "/api/control/joint/move",
        {"joint": joint, "confirm": "MOVE"},
        timeout=180.0,
    )
    evidence["steps"].append({"name": f"{tag}_move", "ok": True, "result": mv})

    print(f"RELEASE J{joint}")
    rel = _http_json(
        base,
        "POST",
        "/api/control/joint/release",
        {"joint": joint, "confirm": "RELEASE"},
    )
    evidence["steps"].append({"name": f"{tag}_release", "ok": True, "result": rel})

    target = plan.get("target_rad")
    actual = mv.get("actual_rad")
    abs_err = None
    within = False
    if target is not None and actual is not None:
        abs_err = abs(float(actual) - float(target))
        within = bool(abs_err <= POS_ERR_TOL_RAD)
    rec = {
        "index": waypoint["index"],
        "joint": joint,
        "phase": waypoint.get("phase"),
        "step_deg": step_deg,
        "direction": direction,
        "plan": plan,
        "actual_rad": actual,
        "abs_error_rad": abs_err,
        "pos_err_tol_rad": POS_ERR_TOL_RAD,
        "within_tol": within,
    }
    if not within:
        raise RuntimeError(
            f"J{joint} move out of tol: abs_err={abs_err} tol={POS_ERR_TOL_RAD} "
            f"target={target} actual={actual}"
        )
    return rec


def _best_effort_close(base: str, evidence: dict[str, Any]) -> None:
    try:
        _http_json(base, "POST", "/api/control/session/close", {})
        evidence["steps"].append({"name": "session_close_best_effort", "ok": True})
    except Exception as close_exc:  # noqa: BLE001
        evidence["steps"].append(
            {"name": "session_close_best_effort", "ok": False, "error": str(close_exc)}
        )


def run_live(
    *,
    base: str,
    authorization_ref: str,
    waypoints: list[dict[str, Any]],
    recover_j6_hold: bool,
    output: Path,
) -> dict[str, Any]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    evidence: dict[str, Any] = {
        "schema_version": "t1-bounded-short-combo-live-0.1",
        "authorization_ref": authorization_ref,
        "stamp_local": stamp,
        "stamp_utc": datetime.now(timezone.utc).isoformat(),
        "block_present": False,
        "control_ready": False,
        "base_url": base,
        "waypoints": waypoints,
        "step_deg_max": MAX_SHORT_COMBO_STEP_DEG,
        "notes": [
            "T1 short combo empty run only: no block, no T2.",
            "control_ready stays false; wrist ranges not marked verified.",
            "Joint-space host_monitor sequence with fail-stop; not H3 PlanBundle.",
            "Outbound then return near start (direction +1 then -1).",
            "Optional J6 ENABLE-only hold recover (no MOVE).",
        ],
        "provenance": {
            "trajectory_kind": "joint_space_host_monitor_sequence",
            "not_h3_plan_bundle": True,
            "not_synthetic_fk_ik_bundle": True,
            "urdf_role": "soft_limits_inside_host_monitor_joint_control_only",
            "fk_ik_live_wiring": "not_claimed",
        },
        "steps": [],
        "waypoint_results": [],
        "verdict": "INCOMPLETE",
    }

    try:
        health = _http_json(base, "GET", "/api/health")
        ctrl = _http_json(base, "GET", "/api/control/status")
        evidence["pre_health"] = health
        evidence["pre_control"] = ctrl
        if not health.get("motion_enabled"):
            raise RuntimeError("host_monitor motion_enabled=false; refuse")
        if not ctrl.get("motion_process_enabled"):
            raise RuntimeError("motion_process_enabled=false; refuse")
        if ctrl.get("session_open"):
            raise RuntimeError("control session already open; refuse")
        if ctrl.get("busy"):
            raise RuntimeError("control busy; refuse")

        pre = _http_json(base, "GET", "/api/state")
        evidence["pre_state"] = {
            "arms_left": (pre.get("arms") or {}).get("left"),
            "control": pre.get("control"),
            "meta": pre.get("meta"),
        }
        evidence["steps"].append({"name": "pre_state", "ok": True})
        left = (pre.get("arms") or {}).get("left") or {}
        q = left.get("q_rad") or []
        used = sorted({int(w["joint"]) for w in waypoints})
        for joint in used:
            if joint - 1 >= len(q) or q[joint - 1] is None or not math.isfinite(
                float(q[joint - 1])
            ):
                raise RuntimeError(f"pre-state J{joint} angle missing/non-finite: {q!r}")

        print("OPEN session READY")
        open_res = _http_json(
            base, "POST", "/api/control/session/open", {"confirm": "READY"}
        )
        evidence["steps"].append({"name": "session_open", "ok": True, "result": open_res})

        if recover_j6_hold:
            print("PREPARE J6 step=1.0 (ENABLE-only)")
            prep6 = _http_json(
                base,
                "POST",
                "/api/control/joint/prepare",
                {"joint": 6, "step_deg": 1.0, "direction": 0},
            )
            evidence["steps"].append({"name": "j6_prepare", "ok": True, "result": prep6})
            print("ENABLE J6")
            en6 = _http_json(
                base,
                "POST",
                "/api/control/joint/enable",
                {"joint": 6, "confirm": "ENABLE"},
                timeout=120.0,
            )
            evidence["steps"].append(
                {"name": "j6_enable_hold_recover", "ok": True, "result": en6}
            )
            time.sleep(0.8)
            print("RELEASE J6")
            rel6 = _http_json(
                base,
                "POST",
                "/api/control/joint/release",
                {"joint": 6, "confirm": "RELEASE"},
            )
            evidence["steps"].append({"name": "j6_release", "ok": True, "result": rel6})

        for wp in waypoints:
            rec = _run_waypoint(base, evidence, wp)
            evidence["waypoint_results"].append(rec)
            print(
                f"wp{wp['index']} J{wp['joint']} {wp.get('phase')} PASS "
                f"abs_err={rec['abs_error_rad']:.6g} rad"
            )

        print("CLOSE session")
        close_res = _http_json(base, "POST", "/api/control/session/close", {})
        evidence["steps"].append({"name": "session_close", "ok": True, "result": close_res})

        post = _http_json(base, "GET", "/api/state")
        evidence["post_state"] = {
            "arms_left": (post.get("arms") or {}).get("left"),
            "control": post.get("control"),
        }

        all_ok = len(evidence["waypoint_results"]) == len(waypoints) and all(
            bool(r.get("within_tol")) for r in evidence["waypoint_results"]
        )
        if all_ok:
            evidence["verdict"] = "PASS"
            evidence["t1_subset"] = "short_combo_out_and_back_joint_space"
        else:
            evidence["verdict"] = "FAIL_OR_INCONCLUSIVE"
    except Exception as exc:  # noqa: BLE001
        evidence["verdict"] = "FAIL"
        evidence["error"] = f"{type(exc).__name__}: {exc}"
        evidence["steps"].append({"name": "exception", "ok": False, "error": evidence["error"]})
        _best_effort_close(base, evidence)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    evidence["host_evidence_path"] = str(output)
    # Rewrite with path recorded.
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("EVIDENCE", output)
    print("VERDICT", evidence.get("verdict"))
    return evidence


def main() -> int:
    p = argparse.ArgumentParser(__doc__)
    p.add_argument(
        "--joints",
        default="1,2,3",
        help="comma joints for out-and-back (default 1,2,3)",
    )
    p.add_argument(
        "--step-deg",
        type=float,
        default=1.0,
        help=f"per-waypoint step degrees (0, {MAX_SHORT_COMBO_STEP_DEG}]",
    )
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--rest-capture", type=Path, default=None)
    p.add_argument(
        "--enable-live-motion",
        action="store_true",
        help="explicit live path via host_monitor (default OFF)",
    )
    p.add_argument(
        "--authorization-ref",
        default=DEFAULT_AUTH,
        help="required non-empty for live motion",
    )
    p.add_argument(
        "--base-url",
        default="http://127.0.0.1:8088",
        help="host_monitor base URL (live only)",
    )
    p.add_argument(
        "--no-recover-j6-hold",
        action="store_true",
        help="skip optional J6 ENABLE-only hold recover (default: recover)",
    )
    args = p.parse_args()
    recover_j6_hold = not bool(args.no_recover_j6_hold)

    joints = tuple(int(x.strip()) for x in str(args.joints).split(",") if x.strip())
    waypoints = default_short_combo_waypoints(joints=joints, step_deg=float(args.step_deg))
    rest_capture = None
    if args.rest_capture is not None:
        rest_capture = json.loads(args.rest_capture.read_text(encoding="utf-8"))
    prereq = evaluate_t1_prerequisites(rest_capture=rest_capture)
    dry = build_t1_short_combo_dry_plan(
        waypoints=waypoints,
        rest_capture=rest_capture,
        prerequisites=prereq,
        motion_enabled=bool(args.enable_live_motion),
        authorization_ref=args.authorization_ref,
    )

    if not args.enable_live_motion:
        payload = {
            "schema_version": "t1-bounded-short-combo-dry-0.1",
            "verdict": "DRY_PLAN_ONLY",
            "control_ready": False,
            "motion_enabled": False,
            "dry_plan": dry,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps({"verdict": "DRY_PLAN_ONLY", "output": str(args.output)}, indent=2))
        return 0

    if not str(args.authorization_ref).strip():
        print("refuse live: empty --authorization-ref", file=sys.stderr)
        return 2

    evidence = run_live(
        base=str(args.base_url),
        authorization_ref=str(args.authorization_ref),
        waypoints=list(dry["waypoints"]),
        recover_j6_hold=recover_j6_hold,
        output=args.output,
    )
    return 0 if evidence.get("verdict") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
