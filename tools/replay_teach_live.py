#!/usr/bin/env python3
"""Replay one manual-teach JSONL on the left P7 and left O6.

The arm path keeps every recorded pose in order.  Host-side interpolation
stretches only segments that would exceed the requested stream speed.  Targets
are bounded to the limits reported by the live P7 SDK before being sent.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import signal
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def post_json(url: str, body: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("record", type=Path)
    parser.add_argument("--speed-rad-s", type=float, default=0.25)
    parser.add_argument("--tick-s", type=float, default=0.02)
    parser.add_argument("--hand-url", default="http://127.0.0.1:8091")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--release-known-reader",
        action="store_true",
        help="stop the exact arm_angle_readonly.py:8094 process before opening can2",
    )
    parser.add_argument(
        "--keep-enabled",
        action="store_true",
        help="leave the arm enabled after replay; default is to disable it",
    )
    args = parser.parse_args()

    rows = [json.loads(line) for line in args.record.read_text(encoding="utf-8").splitlines()]
    samples = [row for row in rows if row.get("type") == "sample"]
    hand_events = sorted(
        [row for row in rows if row.get("type") == "hand"],
        key=lambda row: float(row["t_mono"]),
    )
    if not samples:
        raise SystemExit("record has no samples")
    if not (0.02 <= args.speed_rad_s <= 0.5):
        raise SystemExit("speed-rad-s must be within [0.02, 0.5]")
    if not (0.01 <= args.tick_s <= 0.05):
        raise SystemExit("tick-s must be within [0.01, 0.05]")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    log = args.output.open("x", encoding="utf-8", buffering=1)

    def emit(**payload: object) -> None:
        payload = {"utc": datetime.now(timezone.utc).isoformat(), **payload}
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        print(line, flush=True)
        log.write(line + "\n")

    arm = None
    hand_opened_here = False
    try:
        if args.release_known_reader:
            exact_reader = (
                "/home/qwer/p7_sdk_venv/bin/python -u /tmp/arm_angle_readonly.py "
                "--bind 10.157.173.135 --port 8094"
            )
            found = subprocess.run(
                ["pgrep", "-f", f"^{exact_reader}$"],
                capture_output=True,
                text=True,
                check=False,
            )
            reader_pids = [int(item) for item in found.stdout.split() if item.isdigit()]
            for pid in reader_pids:
                os.kill(pid, signal.SIGTERM)
            deadline = time.monotonic() + 3.0
            while reader_pids and time.monotonic() < deadline:
                reader_pids = [pid for pid in reader_pids if Path(f"/proc/{pid}").exists()]
                if reader_pids:
                    time.sleep(0.05)
            if reader_pids:
                raise RuntimeError(f"read-only can2 owner did not exit: {reader_pids}")
            emit(event="known_reader_released", pids=reader_pids)

        from linkerbot import P7

        arm = P7(side="left", interface_name="can2")
        limits = [(float(lo), float(hi)) for lo, hi in arm._kx.get_joint_limits()]

        clipped_count = 0
        bounded: list[tuple[float, list[float]]] = []
        for row in samples:
            q_in = [float(v) for v in row["q_rad"]]
            if len(q_in) != 7 or not all(math.isfinite(v) for v in q_in):
                raise RuntimeError(f"invalid q at sample {row.get('i')}")
            q_out = [min(max(v, lo), hi) for v, (lo, hi) in zip(q_in, limits)]
            if q_out != q_in:
                clipped_count += 1
            bounded.append((float(row["t_mono"]), q_out))

        current = [float(v) for v in arm.get_angles()]
        emit(
            event="prepared",
            record=str(args.record),
            samples=len(bounded),
            hand_events=len(hand_events),
            speed_rad_s=args.speed_rad_s,
            tick_s=args.tick_s,
            sdk_limits=limits,
            bounded_samples=clipped_count,
            current_q=current,
            first_q=bounded[0][1],
            last_q=bounded[-1][1],
        )

        hand_state = get_json(args.hand_url + "/api/state").get("state", {})
        if not hand_state.get("session_open"):
            post_json(args.hand_url + "/api/session/open", {"confirm": "READY"})
            hand_opened_here = True

        arm.enable()
        arm.set_velocities([args.speed_rad_s] * 7)
        arm.set_accelerations([1.0] * 7)
        emit(event="enabled", q=[float(v) for v in arm.get_angles()])

        # Approach the first taught pose through the SDK's own host-streamed
        # move_j.  This is part of the replay and uses the same speed bound.
        arm.move_j(bounded[0][1], blocking=True)
        emit(event="at_record_start", q=[float(v) for v in arm.get_angles()])

        # Match P7.move_j's pass-through setup, while this script performs the
        # bounded host interpolation and validates every waypoint.
        arm.set_velocities([1.0] * 7)
        arm.set_accelerations([1.0] * 7)
        previous_t, previous_q = bounded[0]
        event_index = 0
        sent = 0
        replay_started = time.monotonic()

        for source_t, target_q in bounded[1:]:
            source_dt = max(0.0, source_t - previous_t)
            max_delta = max(abs(b - a) for a, b in zip(previous_q, target_q))
            duration = max(source_dt, max_delta / args.speed_rad_s)
            steps = max(1, math.ceil(duration / args.tick_s))
            deadline = time.monotonic()
            for step in range(1, steps + 1):
                fraction = step / steps
                waypoint = [a + (b - a) * fraction for a, b in zip(previous_q, target_q)]
                deadline += duration / steps
                time.sleep(max(0.0, deadline - time.monotonic()))
                arm._set_angles(waypoint, check_limits=True)
                sent += 1

            while event_index < len(hand_events) and float(hand_events[event_index]["t_mono"]) <= source_t:
                event = hand_events[event_index]
                result = post_json(
                    args.hand_url + "/api/apply",
                    {
                        "angles_percent": list(event["target_percent"]),
                        "speed_percent": float(event.get("speed_percent", 12.0)),
                        "confirm": "APPLY",
                    },
                )
                emit(event="hand", action=event.get("action"), result=result)
                event_index += 1

            previous_t, previous_q = source_t, target_q

        final_q = [float(v) for v in arm.get_angles()]
        emit(
            event="completed",
            elapsed_s=time.monotonic() - replay_started,
            streamed_waypoints=sent,
            final_q=final_q,
            final_error_rad=max(abs(a - b) for a, b in zip(final_q, bounded[-1][1])),
        )
    except KeyboardInterrupt:
        if arm is not None:
            arm.emergency_stop()
        emit(event="interrupted", hold_requested=arm is not None)
        raise
    except Exception as exc:
        if arm is not None:
            try:
                arm.emergency_stop()
            except Exception:
                pass
        emit(event="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        if hand_opened_here:
            try:
                post_json(args.hand_url + "/api/session/close", {})
            except Exception:
                pass
        if arm is not None:
            try:
                if not args.keep_enabled:
                    arm.disable()
                    emit(event="disabled")
            except Exception as exc:
                try:
                    emit(event="disable_failed", error=f"{type(exc).__name__}: {exc}")
                except Exception:
                    pass
            try:
                arm.close()
            except Exception:
                pass
        log.close()


if __name__ == "__main__":
    main()

