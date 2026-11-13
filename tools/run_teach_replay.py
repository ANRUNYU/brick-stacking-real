#!/usr/bin/env python3
"""Upload and replay a manual-teach JSONL on the robot Linux host.

Run this file on Windows.  OpenSSH scp/ssh will prompt for the Linux password
when key authentication is not configured.  The live executor always targets
left P7 can2 and the existing left O6 service on can1.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


def check_record(path: Path) -> tuple[int, str]:
    samples = 0
    schema = ""
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            row = json.loads(line)
            if line_number == 1:
                schema = str(row.get("schema", ""))
                if row.get("type") != "header" or schema != "manual-teach-stream-1":
                    raise ValueError("不是 manual-teach-stream-1 录制文件")
                if row.get("side") != "left" or row.get("arm_interface") != "can2":
                    raise ValueError("当前执行器仅支持 left/can2 录制")
            if row.get("type") == "sample":
                q = row.get("q_rad")
                if not isinstance(q, list) or len(q) != 7:
                    raise ValueError(f"第 {line_number} 行 q_rad 不是 7 轴")
                samples += 1
    if samples == 0:
        raise ValueError("录制文件没有 sample")
    return samples, schema


def run(command: list[str]) -> None:
    printable = " ".join(command)
    print(f"> {printable}", flush=True)
    subprocess.run(command, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="上传 manual-teach JSONL 并真实复现左臂/左手动作"
    )
    parser.add_argument("record", type=Path, help="录制生成的 .jsonl 文件")
    parser.add_argument("--host", default="10.157.173.135")
    parser.add_argument("--user", default="qwer")
    parser.add_argument("--speed-rad-s", type=float, default=0.25)
    parser.add_argument("--tick-s", type=float, default=0.02)
    parser.add_argument(
        "--keep-enabled",
        action="store_true",
        help="复现结束后不失能；默认自动失能并释放 can2",
    )
    args = parser.parse_args()

    record = args.record.expanduser().resolve()
    if not record.is_file():
        raise SystemExit(f"文件不存在: {record}")
    if not (0.02 <= args.speed_rad_s <= 0.5):
        raise SystemExit("--speed-rad-s 必须在 0.02 到 0.5 之间")
    samples, schema = check_record(record)
    digest = hashlib.sha256(record.read_bytes()).hexdigest()
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", record.name)
    remote_root = "/home/qwer/teach_replays"
    remote_record = f"{remote_root}/{digest[:12]}-{safe_name}"
    remote_executor = f"{remote_root}/replay_teach_live.py"
    remote_log = f"{remote_root}/logs/{digest[:12]}-{record.stem}.jsonl"
    executor = Path(__file__).with_name("replay_teach_live.py").resolve()
    target = f"{args.user}@{args.host}"

    print(
        json.dumps(
            {
                "record": str(record),
                "schema": schema,
                "samples": samples,
                "sha256": digest,
                "robot": "left P7 / can2",
                "hand": "left O6 / can1",
                "disable_after": not args.keep_enabled,
                "remote_log": remote_log,
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )

    run(["ssh", target, "mkdir", "-p", remote_root, f"{remote_root}/logs"])
    run(["scp", str(record), f"{target}:{remote_record}"])
    run(["scp", str(executor), f"{target}:{remote_executor}"])

    remote_command = [
        "/home/qwer/p7_sdk_venv/bin/python",
        "-u",
        remote_executor,
        remote_record,
        "--speed-rad-s",
        str(args.speed_rad_s),
        "--tick-s",
        str(args.tick_s),
        "--release-known-reader",
        "--output",
        remote_log,
    ]
    if args.keep_enabled:
        remote_command.append("--keep-enabled")
    run(["ssh", "-t", target, *remote_command])
    print(f"复现完成。主机日志: {remote_log}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from exc

