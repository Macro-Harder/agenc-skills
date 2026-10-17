#!/usr/bin/env python3
"""Scan subagent results for escalations and print a triage table.

Usage: triage_escalations.py OUT_DIR [--worktrees DIR]

Reads OUT_DIR/<unit>.json (AgenC --output-format json results) and, if
present, OUT_DIR/<unit>.exit, OUT_DIR/<unit>.redispatch (lead re-dispatch
count) and an ESCALATION.json the subagent left in DIR/wt-<unit>/.
An escalation is a finalMessage whose first line is ESCALATION followed by
one JSON object, or that ESCALATION.json file.

Exit codes: 0 nothing needs the lead, 1 escalations or failures to triage,
2 usage error. Python 3.8+ standard library only.
"""
import argparse
import glob
import json
import os
import sys

REQUIRED = ("unit", "goal", "blocker", "question", "options", "recommendation", "partial")
MAX_REDISPATCH = 2


def parse_escalation(text):
    """Return (dict, error). Accepts 'ESCALATION' then a JSON object."""
    text = (text or "").strip()
    if not text.startswith("ESCALATION"):
        return None, None
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return None, "ESCALATION without a JSON object"
    try:
        esc = json.loads(text[start:end + 1])
    except ValueError as e:
        return None, f"ESCALATION JSON invalid: {e.msg}"
    missing = [k for k in REQUIRED if k not in esc]
    return esc, (f"missing fields: {', '.join(missing)}" if missing else None)


def read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def main():
    ap = argparse.ArgumentParser(description="Triage subagent escalations.")
    ap.add_argument("out_dir")
    ap.add_argument("--worktrees", help="dir holding wt-<unit> worktrees")
    a = ap.parse_args()
    files = sorted(glob.glob(os.path.join(a.out_dir, "*.json")))
    files = [f for f in files if not f.endswith(".escalation.json")]
    if not files:
        print(f"no result files in {a.out_dir}", file=sys.stderr)
        return 2
    rows, details, need = [], [], 0
    for f in files:
        unit = os.path.basename(f)[:-5]
        exit_code = read(os.path.join(a.out_dir, unit + ".exit"))
        redis = int(read(os.path.join(a.out_dir, unit + ".redispatch")) or 0)
        try:
            d = json.load(open(f))
            msg, code = d.get("finalMessage", ""), d.get("exitCode")
        except (OSError, ValueError):
            msg, code = "", None
        code = exit_code if exit_code is not None else code
        esc, err = parse_escalation(msg)
        if esc is None and a.worktrees:
            p = os.path.join(a.worktrees, f"wt-{unit}", "ESCALATION.json")
            if os.path.exists(p):
                esc, err = parse_escalation("ESCALATION\n" + (read(p) or ""))
        if esc is not None or err:
            status = "ESCALATED" if not err else "ESCALATED(bad)"
            if err:
                action = "agenc-retry"  # broken contract counts as a failed attempt
            elif redis >= MAX_REDISPATCH:
                action = "lead does it or human"
            else:
                action = "lead decides"
        elif code is None:
            status, action = "NO RESULT", "read stderr"
        elif str(code) != "0":
            status, action = f"FAILED({code})", "agenc-retry"
        else:
            status, action = "DONE?", "verify"
        if status != "DONE?":
            need += 1
        first = msg.splitlines()[0] if msg else ""
        q = (esc or {}).get("question") or err or first
        rows.append((unit, str(code), status, f"{redis}/{MAX_REDISPATCH}", action, str(q)[:70]))
        if esc:
            details.append((unit, esc, err))
    w = [max(len(r[i]) for r in rows + [("unit", "exit", "status", "redisp", "next", "question")]) for i in range(6)]
    for r in [("unit", "exit", "status", "redisp", "next", "question")] + rows:
        print("  ".join(c.ljust(w[i]) for i, c in enumerate(r)))
    for unit, esc, err in details:
        print(f"\n== {unit}: blocker={esc.get('blocker')} partial={esc.get('partial')}")
        if err:
            print(f"   contract problem: {err}")
        print(f"   question: {esc.get('question')}")
        for i, o in enumerate(esc.get("options") or [], 1):
            print(f"   option {i}: {o if isinstance(o, str) else json.dumps(o)}")
        print(f"   recommends: {esc.get('recommendation')}")
        for r in esc.get("ruled_out") or []:
            print(f"   ruled out: {r}")
    return 1 if need else 0


if __name__ == "__main__":
    sys.exit(main())
