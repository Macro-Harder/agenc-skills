#!/usr/bin/env python3
"""cost_compare.py - Compare AgenC estimate vs real provider spend (stdlib only)."""

from __future__ import annotations
import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime


def parse_since(s: str) -> datetime:
    s = s.strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s)
    except Exception:
        raise ValueError(f"Cannot parse --since: {s}")


def parse_log_time(line: str):
    m = re.match(r"^(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})", line)
    if not m:
        return None
    ts = m.group(1).replace("T", " ")
    try:
        return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def fmt_files(files):
    if not files:
        return "-"
    names = [os.path.basename(f) for f in files]
    if len(names) <= 2:
        return " ".join(names)
    return f"{names[0]} ... ({len(names)} files)"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch-log", type=str, default=None)
    parser.add_argument("--base", type=float, default=None)
    parser.add_argument("--snapshot-before", type=str, default=None)
    parser.add_argument("--snapshot-after", type=str, default=None)
    parser.add_argument("--since", type=str, default=None)
    parser.add_argument("--sessions", nargs="+", required=True)
    parser.add_argument("--out-jsonl", nargs="*", default=[])
    args = parser.parse_args()

    since_dt = None
    if args.since:
        since_dt = parse_since(args.since)

    # === REAL side ===
    job_total = None
    real_delta = None
    real_desc = ""
    base_str = "0"
    now_str = "0"

    # (a) watch-log
    if args.watch_log and os.path.isfile(args.watch_log):
        try:
            with open(args.watch_log, "r", encoding="utf-8", errors="ignore") as f:
                log_lines = f.readlines()

            base_from_log = None
            last_usage = None
            since_usage = None

            for line in log_lines:
                if "watchdog2 start" in line:
                    m = re.search(r"base=([0-9.]+)", line)
                    if m:
                        base_from_log = float(m.group(1))
                if "usage=" in line:
                    m = re.search(r"usage=([0-9.]+)", line)
                    if m:
                        u = float(m.group(1))
                        last_usage = u
                        if since_dt is not None and since_usage is None:
                            log_dt = parse_log_time(line)
                            if log_dt is not None and log_dt >= since_dt:
                                since_usage = u

            base_val = args.base if args.base is not None else (base_from_log if base_from_log is not None else 0.0)
            if last_usage is not None:
                if since_dt is not None and since_usage is not None:
                    real_delta = last_usage - since_usage
                    base_str = f"{since_usage:.6f}"
                    now_str = f"{last_usage:.6f}"
                else:
                    real_delta = last_usage - base_val
                    base_str = f"{base_val:.6f}"
                    now_str = f"{last_usage:.6f}"
                real_desc = f"watch-log {os.path.basename(args.watch_log)}"
                if since_dt is not None and since_usage is not None:
                    real_desc += f"; window since {args.since}"
                job_total = (last_usage - base_val, base_val, last_usage)
        except Exception:
            pass

    # (b) snapshots (only if no real_delta yet)
    if real_delta is None and args.snapshot_before and args.snapshot_after:
        try:
            with open(args.snapshot_before, "r", encoding="utf-8") as f:
                before = json.load(f)
            with open(args.snapshot_after, "r", encoding="utf-8") as f:
                after = json.load(f)

            b = before.get("usage")
            if b is None and isinstance(before.get("data"), dict):
                b = before.get("data", {}).get("usage")
            a = after.get("usage")
            if a is None and isinstance(after.get("data"), dict):
                a = after.get("data", {}).get("usage")

            if b is not None and a is not None:
                real_delta = float(a) - float(b)
                base_str = f"{float(b):.6f}"
                now_str = f"{float(a):.6f}"
                real_desc = f"snapshots {os.path.basename(args.snapshot_before)} -> {os.path.basename(args.snapshot_after)}"
        except Exception:
            pass

    if real_delta is None:
        print("No real source could be read", file=sys.stderr)
        sys.exit(11)

    # === ESTIMATE side ===
    # rollout files
    rollout_files = []
    for pattern in args.sessions:
        for f in glob.glob(pattern):
            if os.path.isfile(f):
                if since_dt:
                    try:
                        mtime = datetime.fromtimestamp(os.path.getmtime(f))
                        if mtime < since_dt:
                            continue
                    except Exception:
                        pass
                rollout_files.append(f)

    # out-jsonl files
    out_files = []
    for pattern in args.out_jsonl:
        for f in glob.glob(pattern):
            if os.path.isfile(f):
                if since_dt:
                    try:
                        mtime = datetime.fromtimestamp(os.path.getmtime(f))
                        if mtime < since_dt:
                            continue
                    except Exception:
                        pass
                out_files.append(f)

    # Parse rollouts (last session_usage per file)
    rollout_cost = 0.0
    rollout_held = 0.0
    rollout_calls = 0
    rollout_in = 0
    rollout_out = 0

    for fpath in rollout_files:
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            last_payload = None
            for line in reversed(lines):
                try:
                    data = json.loads(line.strip())
                    if data.get("type") == "event_msg":
                        payload = data.get("payload", {})
                        msg = payload.get("msg", {})
                        if msg.get("type") == "session_usage":
                            last_payload = msg.get("payload", {})
                            break
                except Exception:
                    continue
            if last_payload:
                rollout_cost += float(last_payload.get("costUsd", 0.0) or 0.0)
                rollout_held += float(last_payload.get("heldCostUsd", 0.0) or 0.0)
                rollout_calls += int(last_payload.get("modelCalls", 0) or 0)
                rollout_in += int(last_payload.get("inputTokens", 0) or 0)
                rollout_out += int(last_payload.get("outputTokens", 0) or 0)
        except Exception:
            continue

    # Parse out-jsonl (last result tokenUsage per file)
    out_cost = 0.0
    out_in = 0
    out_out = 0
    for fpath in out_files:
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            last_result = None
            for line in reversed(lines):
                try:
                    data = json.loads(line.strip())
                    if data.get("type") == "result":
                        last_result = data
                        break
                except Exception:
                    continue
            if last_result:
                tu = last_result.get("tokenUsage", {})
                out_cost += float(tu.get("costUsd", 0.0) or 0.0)
                out_in += int(tu.get("inputTokens", 0) or 0)
                out_out += int(tu.get("outputTokens", 0) or 0)
        except Exception:
            continue

    total_est = rollout_cost + out_cost
    total_held = rollout_held

    # === Table ===
    print("source       files                              model calls  tokens in/out      est costUsd  est heldCostUsd")
    if rollout_files:
        fstr = fmt_files(rollout_files)
        print(f"rollouts     {fstr:<35} {rollout_calls:>11}  {rollout_in:>7}/{rollout_out:<7}  {rollout_cost:>10.4f}  {rollout_held:>10.4f}")
    if out_files:
        fstr = fmt_files(out_files)
        print(f"out-jsonl    {fstr:<35} {0:>11}  {out_in:>7}/{out_out:<7}  {out_cost:>10.4f}  {0:>10.4f}")

    # === Summary lines ===
    print(f"REAL   ${real_delta:.6f}  (provider key usage delta; {real_desc}; base {base_str} -> now {now_str})")
    print(f"EST    ${total_est:.6f}  (AgenC costUsd sum, estimate)")

    if real_delta <= 0.0001:
        print("real ~$0, ratio undefined")
    else:
        ratio = total_est / real_delta
        print(f"RATIO  est/real = {ratio:.1f}x")

    if job_total is not None:
        print(f"JOB    ${job_total[0]:.6f}  (whole job on this key: watcher base {job_total[1]:.6f} -> now {job_total[2]:.6f})")
    print("Report REAL. Never report costUsd as spend.")
    sys.exit(0)


if __name__ == "__main__":
    main()
