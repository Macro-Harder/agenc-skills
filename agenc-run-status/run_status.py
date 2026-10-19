#!/usr/bin/env python3
"""run_status.py - read-only snapshot of a supervised AgenC lead run (stdlib only)."""

from __future__ import annotations
import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def parse_log_timestamp(line: str) -> datetime | None:
    match = re.match(r'^(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})', line)
    if not match:
        return None
    ts_str = match.group(1)
    try:
        if 'T' in ts_str:
            return datetime.strptime(ts_str, '%Y-%m-%dT%H:%M:%S')
        else:
            return datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return None


def get_age_minutes(dt: datetime | None) -> float | None:
    if dt is None:
        return None
    now = datetime.now()
    delta = now - dt
    return delta.total_seconds() / 60.0


def read_tail(path: Path, max_bytes: int = 2 * 1024 * 1024) -> str:
    if not path.is_file():
        return ""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            if size == 0:
                return ""
            read_size = min(max_bytes, size)
            f.seek(max(0, size - read_size))
            data = f.read(read_size)
            text = data.decode("utf-8", errors="replace")
            if size > read_size:
                first_nl = text.find("\n")
                if first_nl != -1:
                    text = text[first_nl + 1 :]
            return text
    except Exception:
        return ""


def get_lines(path: Path, max_bytes: int = 2 * 1024 * 1024) -> list[str]:
    text = read_tail(path, max_bytes)
    return [line for line in text.splitlines() if line.strip()]


def get_last_n_timestamped(path: Path, n: int) -> list[str]:
    lines = get_lines(path)
    ts_lines = [l for l in lines if parse_log_timestamp(l) is not None]
    return ts_lines[-n:]


def find_launcher_pid(job: str | None) -> int | None:
    if not job:
        return None
    try:
        for entry in Path("/proc").iterdir():
            if not entry.is_dir() or not entry.name.isdigit():
                continue
            try:
                cmdline_path = entry / "cmdline"
                if cmdline_path.exists():
                    cmdline = cmdline_path.read_bytes().decode("utf-8", errors="replace").replace("\0", " ")
                    if "launch_lead.sh" in cmdline and f"--job {job}" in cmdline:
                        return int(entry.name)
            except Exception:
                continue
    except Exception:
        pass
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--meta", default=os.environ.get("AGENC_META"))
    parser.add_argument("--agenc-home", default=str(Path.home() / ".agenc"))
    parser.add_argument("--lines", type=int, default=3)
    parser.add_argument("--wedge-min", type=int, default=10)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if not args.meta:
        print("Error: --meta or AGENC_META required", file=sys.stderr)
        sys.exit(1)

    meta = Path(args.meta).expanduser().resolve()
    agenc_home = Path(args.agenc_home).expanduser().resolve()
    lines_n = args.lines
    wedge_min = args.wedge_min

    supervisor_log = meta / "supervisor.log"
    child_broker_log = meta / "child_broker.log"
    budget_log = meta / "budget_watch.log"

    sup_lines = get_lines(supervisor_log)
    broker_lines = get_lines(child_broker_log)
    budget_lines = get_lines(budget_log)

    # SUPERVISOR
    supervisor_pid = None
    last_ts = None
    launch_job = None
    launch_model = None
    launch_config = None
    launch_cwd = None
    lead_launch_time = None
    relaunch_count = 0
    stall_count = 0

    for i, line in enumerate(sup_lines):
        ts = parse_log_timestamp(line)
        if ts:
            last_ts = ts
        pid_m = re.search(r"\[supervisor (\d+)\]", line)
        if pid_m:
            if supervisor_pid is not None and int(pid_m.group(1)) != supervisor_pid:
                relaunch_count = stall_count = 0  # count for the current supervisor only
            supervisor_pid = int(pid_m.group(1))
        if "] RELAUNCH" in line:
            relaunch_count += 1
        if "] STALL" in line:
            stall_count += 1
        if "launch " in line and " model " in line and " config " in line:
            m = re.search(r"launch (\S+) model (\S+) config (\S+)", line)
            if m:
                j = m.group(1)
                mo = m.group(2)
                c = m.group(3)
                cwd = None
                for k in range(i + 1, min(i + 6, len(sup_lines))):
                    cl = sup_lines[k]
                    cm = re.search(r"\(run in cwd=([^;)]+)", cl)
                    if cm:
                        cwd = cm.group(1)
                        break
                    if parse_log_timestamp(cl):
                        break
                launch_job = j
                launch_model = mo
                launch_config = c
                launch_cwd = cwd
                if ts:
                    lead_launch_time = ts

    sup_alive = bool(supervisor_pid and os.path.exists(f"/proc/{supervisor_pid}"))
    sup_age = get_age_minutes(last_ts)

    # LEAD launcher
    launcher_pid = find_launcher_pid(launch_job)
    launcher_alive = bool(launcher_pid and os.path.exists(f"/proc/{launcher_pid}"))

    # CHILDREN from broker
    launched_children = []
    for line in broker_lines:
        if "launched " in line:
            m = re.search(
                r"launched .*?: role (\S+) model (\S+) .*? out (\S+) .*? pid (\d+)",
                line,
            )
            if m:
                launched_children.append(
                    {
                        "role": m.group(1),
                        "model": m.group(2),
                        "out_dir": m.group(3),
                        "pid": int(m.group(4)),
                    }
                )

    live_children = []
    for ch in launched_children:
        pid = ch["pid"]
        out_dir = Path(ch["out_dir"])
        has_exit = (out_dir / "exit").exists()
        alive = os.path.exists(f"/proc/{pid}") and not has_exit
        if alive:
            out_jsonl = out_dir / "out.jsonl"
            idle_min = None
            if out_jsonl.exists():
                try:
                    mtime = out_jsonl.stat().st_mtime
                    idle_min = (time.time() - mtime) / 60.0
                except Exception:
                    pass
            wedged = idle_min is not None and idle_min > wedge_min
            live_children.append(
                {
                    "role": ch["role"],
                    "model": ch["model"],
                    "out_dir": str(out_dir),
                    "pid": pid,
                    "idle_minutes": round(idle_min, 1) if idle_min is not None else None,
                    "wedged": wedged,
                }
            )

    # Finished children since lead launch
    finished_since = 0
    exit_summary: dict = defaultdict(int)
    if lead_launch_time is None:
        lead_launch_time = datetime.now() - __import__("datetime").timedelta(days=1)
    for ch in launched_children:
        out_dir = Path(ch["out_dir"])
        exit_file = out_dir / "exit"
        if exit_file.exists():
            try:
                exit_mtime = exit_file.stat().st_mtime
                exit_dt = datetime.fromtimestamp(exit_mtime)
                if exit_dt >= lead_launch_time.replace(tzinfo=None):
                    code_str = exit_file.read_text(errors="replace").strip()
                    try:
                        code = int(code_str)
                    except Exception:
                        code = code_str
                    exit_summary[code] += 1
                    finished_since += 1
            except Exception:
                pass

    # SESSION
    chosen_rollout = None
    session_mtime = None
    if launch_cwd:
        safe_cwd = launch_cwd.replace("/", "-")
        proj_glob = f"v2-{safe_cwd}-*"
        projects_dir = agenc_home / "projects"
        recent_rollouts = []
        now_ts = time.time()
        for proj in projects_dir.glob(proj_glob):
            if not proj.is_dir():
                continue
            for rollout in proj.glob("sessions/*/rollout-*.jsonl"):
                try:
                    st = rollout.stat()
                    if now_ts - st.st_mtime < 7200:
                        recent_rollouts.append((st.st_size, st.st_mtime, rollout))
                except Exception:
                    continue
        # Lead heuristic: the first rollout created at or after the supervisor's
        # last "launch" line (children start later). File names carry UTC ISO time.
        after = []
        if lead_launch_time is not None:
            from datetime import timezone
            lt = lead_launch_time if lead_launch_time.tzinfo else lead_launch_time.astimezone()
            for size, mt, r in recent_rollouts:
                m = re.search(r"rollout-(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-(\d{2})", r.name)
                if not m:
                    continue
                created = datetime.strptime(" ".join(m.groups()), "%Y-%m-%d %H %M %S").replace(tzinfo=timezone.utc)
                if created >= lt.astimezone(timezone.utc).replace(microsecond=0):
                    after.append((created, size, mt, r))
        if after:
            after.sort()
            chosen_rollout, session_mtime = after[0][3], after[0][2]
        elif recent_rollouts:
            recent_rollouts.sort(key=lambda x: x[0], reverse=True)
            chosen_rollout = recent_rollouts[0][2]
            session_mtime = recent_rollouts[0][1]

    model_calls = 0
    last_session_usage = None
    last_agent_message = None
    last_tool_call_args = None
    last_error_info = None

    if chosen_rollout:
        rollout_lines = get_lines(chosen_rollout, max_bytes=4 * 1024 * 1024)
        for line in rollout_lines:
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if not isinstance(ev, dict):
                continue
            ev_type = ev.get("type")
            if ev_type == "token_count":
                model_calls += 1
            elif ev_type == "event_msg":
                payload = ev.get("payload", {})
                msg = payload.get("msg", {})
                msg_type = msg.get("type")
                if msg_type == "token_count":
                    model_calls += 1
                elif msg_type == "session_usage":
                    last_session_usage = msg.get("payload", {})
                elif msg_type == "agent_message":
                    last_agent_message = msg.get("payload", {}).get("message", "")
                elif msg_type == "tool_call_started":
                    last_tool_call_args = msg.get("payload", {}).get("args", "")
                elif msg_type in ("error", "stream_error"):
                    last_error_info = msg.get("payload", str(msg))
            elif ev_type in ("error", "stream_error"):
                last_error_info = ev.get("payload", str(ev))

    # REAL SPEND
    last_usage = None
    last_delta = None
    watching_pids = []
    last_watchdog_line = None
    stop_val = None
    headroom = None

    for line in reversed(budget_lines):
        if "usage=" in line and last_usage is None:
            m = re.search(r"usage=([\d.]+)\s+delta=([\d.]+)\s+watching:\s*([\d\s]+)", line)
            if m:
                last_usage = float(m.group(1))
                last_delta = float(m.group(2))
                watching_pids = [p for p in m.group(3).strip().split() if p]
        if "watchdog2 start" in line and last_watchdog_line is None:
            last_watchdog_line = line
            sm = re.search(r"STOP=([\d.]+)", line)
            if sm:
                stop_val = float(sm.group(1))

    if stop_val is not None and last_delta is not None:
        headroom = stop_val - last_delta

    # Output
    if args.json:
        result = {
            "supervisor": {
                "pid": supervisor_pid,
                "alive": sup_alive,
                "last_line_age_min": round(sup_age, 2) if sup_age is not None else None,
            },
            "lead": {
                "job": launch_job,
                "model": launch_model,
                "config": launch_config,
                "cwd": launch_cwd,
                "relaunch_count": relaunch_count,
                "stall_count": stall_count,
                "launcher_pid": launcher_pid,
                "launcher_alive": launcher_alive,
            },
            "session": {
                "path": str(chosen_rollout) if chosen_rollout else None,
                "idle_age_min": round((time.time() - session_mtime) / 60, 2) if session_mtime else None,
                "model_calls": model_calls,
                "last_session_usage": last_session_usage,
                "last_agent_message": last_agent_message[:300] if last_agent_message else None,
                "last_tool_call_started_args": last_tool_call_args[:200] if last_tool_call_args else None,
                "last_error": str(last_error_info)[:300] if last_error_info else None,
            },
            "children": {
                "live": live_children,
                "finished_since_launch": finished_since,
                "exit_summary": dict(exit_summary),
            },
            "real_spend": {
                "last_usage": last_usage,
                "last_delta": last_delta,
                "watching": watching_pids,
                "last_watchdog_line": last_watchdog_line,
                "headroom_to_stop": round(headroom, 4) if headroom is not None else None,
            },
            "last_logs": {
                "supervisor": get_last_n_timestamped(supervisor_log, lines_n),
                "child_broker": get_last_n_timestamped(child_broker_log, lines_n),
                "budget_watch": get_last_n_timestamped(budget_log, lines_n),
            },
        }
        print(json.dumps(result, indent=2))
        return

    # Human readable
    print("SUPERVISOR:")
    if supervisor_pid is None:
        print("  missing")
    else:
        alive_str = "yes" if sup_alive else "no"
        age_str = f"{sup_age:.1f} min" if sup_age is not None else "unknown"
        print(f"  pid: {supervisor_pid}")
        print(f"  alive: {alive_str}")
        print(f"  last timestamped line age: {age_str}")
    print()

    print("LEAD:")
    if launch_job is None:
        print("  missing")
    else:
        print(f"  job: {launch_job}")
        print(f"  model: {launch_model}")
        print(f"  config: {launch_config}")
        print(f"  cwd: {launch_cwd}")
        print(f"  relaunches (this supervisor): {relaunch_count}")
        print(f"  stalls (this supervisor): {stall_count}")
        if launcher_pid:
            lalive = "yes" if launcher_alive else "no"
            print(f"  launcher pid: {launcher_pid} (alive: {lalive})")
        else:
            print("  launcher pid: not found")
    print()

    print("SESSION:")
    if not chosen_rollout:
        print("  missing")
    else:
        idle = (time.time() - session_mtime) / 60 if session_mtime else None
        print(f"  path: {chosen_rollout}")
        print(f"  idle age: {idle:.1f} min" if idle is not None else "  idle age: unknown")
        print(f"  model calls (token_count): {model_calls}")
        if last_session_usage:
            cu = last_session_usage.get("costUsd", "?")
            hu = last_session_usage.get("heldCostUsd", "?")
            print(f"  last session_usage: costUsd={cu} heldCostUsd={hu} (AgenC ESTIMATE, not real spend)")
        else:
            print("  last session_usage: none")
        if last_agent_message:
            print(f"  last agent_message: {last_agent_message[:300]}")
        else:
            print("  last agent_message: none")
        if last_tool_call_args:
            print(f"  last tool_call_started args: {last_tool_call_args[:200]}")
        else:
            print("  last tool_call_started args: none")
        if last_error_info:
            print(f"  last error/stream_error: {str(last_error_info)[:300]}")
        else:
            print("  last error/stream_error: none")
    print()

    print("CHILDREN:")
    if not live_children:
        print("  (no live children)")
    else:
        for ch in live_children:
            w = " WEDGED" if ch.get("wedged") else ""
            idle = ch.get("idle_minutes")
            idle_str = f"{idle} min" if idle is not None else "unknown"
            print(f"  role: {ch['role']} model: {ch['model']} out: {ch['out_dir']} pid: {ch['pid']} idle: {idle_str}{w}")
    print(f"  finished children since lead launch: {finished_since}")
    if exit_summary:
        print(f"  exit codes summary: {dict(exit_summary)}")
    print()

    print("REAL SPEND:")
    if last_usage is None:
        print("  missing")
    else:
        print(f"  last usage={last_usage} delta={last_delta} watching: {' '.join(watching_pids)}")
        if last_watchdog_line:
            print(f"  last watchdog2 start: {last_watchdog_line}")
        if headroom is not None:
            print(f"  headroom to STOP: {headroom:.4f}")
    print()

    print("LAST LOG LINES:")
    for name, logp in [
        ("supervisor.log", supervisor_log),
        ("child_broker.log", child_broker_log),
        ("budget_watch.log", budget_log),
    ]:
        print(f"  {name}:")
        lastn = get_last_n_timestamped(logp, lines_n)
        if not lastn:
            print("    missing")
        else:
            for l in lastn:
                print(f"    {l}")
        print()


if __name__ == "__main__":
    main()
