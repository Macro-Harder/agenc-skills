#!/usr/bin/env python3
"""Keep agent jobs under a dollar limit using real provider spend.

Reads cumulative spend from your provider's usage endpoint, never from the
agent's own estimate.

  spend_guard.py snapshot                    record current usage
  spend_guard.py check --limit USD           exit 10 if spend since snapshot > USD
  spend_guard.py run --limit USD -- CMD...   snapshot, run CMD, wait for lagging
                                             usage, report the real delta

Config (flag, then env, then default):
  --url        PROVIDER_USAGE_URL     usage endpoint returning JSON
  --json-path  PROVIDER_USAGE_PATH    dotted path to cumulative USD (data.usage)
  --key-env    SPEND_GUARD_KEY_ENV    name of the env var holding the key (PROVIDER_API_KEY)
  --state      SPEND_GUARD_STATE      snapshot file (~/.local/state/spend-guard/snapshot.json)

The key is sent as "Authorization: Bearer <key>" and is never printed.
Exit codes: check -> 0 within limit, 10 over limit, 11 guard error.
            run   -> the command's exit code, or 10 if over limit, 11 guard error.
Python 3.8+ standard library only.
"""
import argparse
import http.client
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

OVER, ERR = 10, 11


class GuardError(Exception):
    pass


def log(msg):
    print(f"spend_guard: {msg}", file=sys.stderr, flush=True)


def fetch_usage(a):
    if not a.url:
        raise GuardError("no usage URL; set --url or PROVIDER_USAGE_URL")
    key = os.environ.get(a.key_env, "")
    req = urllib.request.Request(a.url, headers={"Accept": "application/json"})
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    elif not a.allow_no_key:
        raise GuardError(f"env var {a.key_env} is empty; set it or pass --key-env")
    try:
        with urllib.request.urlopen(req, timeout=a.timeout) as r:
            body = json.load(r)
    except urllib.error.HTTPError as e:
        raise GuardError(f"usage endpoint returned HTTP {e.code}") from None
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as e:
        raise GuardError(f"usage endpoint unreadable: {type(e).__name__}") from None
    node = body
    for part in a.json_path.split("."):
        try:
            node = node[int(part)] if isinstance(node, list) else node[part]
        except (KeyError, IndexError, ValueError, TypeError):
            raise GuardError(f"json path {a.json_path!r} not found in response") from None
    try:
        return float(node)
    except (TypeError, ValueError):
        raise GuardError(f"value at {a.json_path!r} is not a number") from None


def save_snapshot(a, usage):
    os.makedirs(os.path.dirname(os.path.abspath(a.state)), exist_ok=True)
    tmp = a.state + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"usage": usage, "time": time.time(), "url": a.url, "json_path": a.json_path}, f)
    os.replace(tmp, a.state)


def load_snapshot(a):
    try:
        with open(a.state) as f:
            return float(json.load(f)["usage"])
    except (OSError, ValueError, KeyError):
        raise GuardError(f"no readable snapshot at {a.state}; run 'snapshot' first") from None


def report(start, now, limit):
    delta = now - start
    state = "OVER" if delta > limit else "ok"
    print(f"spend_guard: start={start:.6f} now={now:.6f} delta={delta:.6f} limit={limit:.6f} {state}",
          flush=True)
    return delta


def cmd_snapshot(a):
    u = fetch_usage(a)
    save_snapshot(a, u)
    print(f"spend_guard: snapshot usage={u:.6f} saved to {a.state}")
    return 0


def cmd_check(a):
    start = load_snapshot(a)
    delta = report(start, fetch_usage(a), a.limit)
    return OVER if delta > a.limit else 0


def settle(a, start, last):
    """Poll until usage moves past `last` and holds steady, or until --settle runs out."""
    deadline = time.time() + a.settle
    seen_change = last > start
    stable = 0
    while time.time() < deadline:
        time.sleep(min(a.poll, max(0.0, deadline - time.time())))
        try:
            now = fetch_usage(a)
        except GuardError as e:
            log(f"settle read failed ({e}); retrying")
            continue
        if now != last:
            seen_change, stable, last = True, 0, now
        else:
            stable += 1
        if seen_change and stable >= 2:
            break
    if not seen_change:
        log(f"usage did not move within {a.settle:.0f}s; it may still be lagging. Re-check later.")
    return last


def stop(proc, sig):
    try:
        os.killpg(proc.pid, sig)
    except ProcessLookupError:
        pass


def cmd_run(a):
    cmd = a.command[1:] if a.command[:1] == ["--"] else a.command
    if not cmd:
        raise GuardError("no command given after --")
    start = fetch_usage(a)
    save_snapshot(a, start)
    log(f"snapshot usage={start:.6f}; running: {cmd[0]} ...")
    # Own process group, so stopping the job also stops its children.
    proc = subprocess.Popen(cmd, start_new_session=True)
    last, killed = start, False
    try:
        while proc.poll() is None:
            try:
                proc.wait(timeout=a.poll)
                break
            except subprocess.TimeoutExpired:
                pass
            try:
                last = fetch_usage(a)
            except GuardError as e:
                log(f"mid-run read failed ({e}); continuing")
                continue
            if last - start > a.limit:
                log(f"spend {last - start:.6f} exceeds limit {a.limit:.6f}; stopping the command")
                stop(proc, signal.SIGTERM)
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    stop(proc, signal.SIGKILL)
                    proc.wait()
                killed = True
    finally:
        if proc.poll() is None:  # guard crashed or was interrupted: never leave the job running
            stop(proc, signal.SIGKILL)
            proc.wait()
    rc = proc.returncode
    log(f"command exited {rc}; waiting up to {a.settle:.0f}s for usage to settle")
    final = settle(a, start, last)
    delta = report(start, final, a.limit)
    if killed or delta > a.limit:
        return OVER
    return rc


def main(argv=None):
    ap = argparse.ArgumentParser(description="Keep agent jobs under a dollar limit using real provider spend.")
    ap.add_argument("--url", default=os.environ.get("PROVIDER_USAGE_URL", ""))
    ap.add_argument("--json-path", default=os.environ.get("PROVIDER_USAGE_PATH", "data.usage"))
    ap.add_argument("--key-env", default=os.environ.get("SPEND_GUARD_KEY_ENV", "PROVIDER_API_KEY"))
    ap.add_argument("--allow-no-key", action="store_true", help="call the endpoint without a key")
    ap.add_argument("--state", default=os.environ.get(
        "SPEND_GUARD_STATE", os.path.expanduser("~/.local/state/spend-guard/snapshot.json")))
    ap.add_argument("--timeout", type=float, default=20.0, help="HTTP timeout seconds")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("snapshot", help="record current usage")
    c = sub.add_parser("check", help="compare current usage to the snapshot")
    c.add_argument("--limit", type=float, required=True, help="max USD since snapshot")
    r = sub.add_parser("run", help="run a command under a spend limit")
    r.add_argument("--limit", type=float, required=True, help="max USD for this command")
    r.add_argument("--poll", type=float, default=15.0, help="seconds between usage reads")
    r.add_argument("--settle", type=float, default=120.0, help="max seconds to wait for lagging usage")
    r.add_argument("command", nargs=argparse.REMAINDER, help="-- command to run")
    a = ap.parse_args(argv)
    try:
        return {"snapshot": cmd_snapshot, "check": cmd_check, "run": cmd_run}[a.cmd](a)
    except GuardError as e:
        log(f"error: {e}")
        return ERR


if __name__ == "__main__":
    sys.exit(main())
