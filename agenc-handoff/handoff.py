#!/usr/bin/env python3
"""Create, check, and move handoff packets.

Usage:
  handoff.py new --root DIR --from A --to B
  handoff.py check PATH
  handoff.py move PATH --status complete|partial|blocked

Packets live in DIR/New, DIR/Incomplete, DIR/Complete and are named
{A}-to-{B}-HANDOFF-{n}.md, with n the next free number for that pair
across all three folders.

Exit codes: 0 ok, 1 packet incomplete or refused, 2 usage error.
Python 3.8+ standard library only.
"""
import argparse
import os
import re
import sys

FOLDERS = ("New", "Incomplete", "Complete")
STATUSES = ("complete", "partial", "blocked")
FIELDS = (
    ("TASK", "What you were asked to do, in one or two sentences."),
    ("STATUS", "complete | partial | blocked"),
    ("OUTPUT", "Paths to the deliverables. One per line."),
    ("BASE", "Code: repo, base ref (commit sha), branch, worktree path. Otherwise: none."),
    ("VERIFY", "The exact command you ran, then its literal result. Or: not run, because ..."),
    ("COST", "Real spend from the provider usage endpoint, and whether it settled. Or: none."),
    ("SOURCES", "Files, links, logs, and timestamps you worked from."),
    ("DECISIONS", "Judgment calls you made, and why."),
    ("UNCERTAINTIES", "What you could not verify."),
    ("NEXT OWNER", "Who continues, and the first thing they should do."),
    ("DO NOT ASSUME", "Facts the receiver must re-check before relying on them."),
)
REQUIRED = [name for name, _ in FIELDS]
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._]*(?:-[A-Za-z0-9._]+)*$")
HEADING_RE = re.compile(r"^##\s+(.+?)\s*$")
PLACEHOLDER_RE = re.compile(r"^<.*>$")
SECRET_RE = re.compile(
    r"(-----BEGIN [A-Z ]*PRIVATE KEY-----|\bsk-[A-Za-z0-9_-]{16,}|\bAKIA[0-9A-Z]{16}\b"
    r"|\bgh[pousr]_[A-Za-z0-9]{20,}|(?i:\b(?:api[_-]?key|token|password|secret)\s*[:=]\s*\S{8,}))"
)


def die(msg, code=2):
    print(msg, file=sys.stderr)
    sys.exit(code)


def check_name(label, value):
    if not NAME_RE.match(value) or "-to-" in value:
        die(f"bad {label} name {value!r}: use letters, digits, '.', '_', '-' and no '-to-'")


def template(sender, receiver, n):
    lines = [f"# HANDOFF {n}: {sender} -> {receiver}", ""]
    for name, hint in FIELDS:
        lines += [f"## {name}", f"<{hint}>", ""]
    return "\n".join(lines)


def parse(text):
    """Return {FIELD: body} for each '## FIELD' section."""
    sections, current = {}, None
    for line in text.splitlines():
        m = HEADING_RE.match(line)
        if m:
            current = m.group(1).upper()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items()}


def is_empty(body):
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    return not lines or all(PLACEHOLDER_RE.match(ln) for ln in lines)


def problems(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    sections, out = parse(text), []
    for name in REQUIRED:
        if name not in sections:
            out.append(f"missing: {name}")
        elif is_empty(sections[name]):
            out.append(f"empty: {name}")
    status = sections.get("STATUS", "")
    if status and not is_empty(status) and status.strip().lower() not in STATUSES:
        out.append(f"bad STATUS {status.strip()!r}: use {' | '.join(STATUSES)}")
    for i, line in enumerate(text.splitlines(), 1):
        if SECRET_RE.search(line):
            out.append(f"possible secret on line {i}: remove it, name the env var instead")
    return out


def cmd_new(args):
    check_name("--from", args.sender)
    check_name("--to", args.receiver)
    pat = re.compile(re.escape(f"{args.sender}-to-{args.receiver}-HANDOFF-") + r"(\d+)\.md$")
    used = []
    for folder in FOLDERS:
        d = os.path.join(args.root, folder)
        os.makedirs(d, exist_ok=True)
        used += [int(m.group(1)) for m in map(pat.match, os.listdir(d)) if m]
    n = max(used, default=0) + 1
    path = os.path.join(args.root, "New", f"{args.sender}-to-{args.receiver}-HANDOFF-{n}.md")
    with open(path, "x", encoding="utf-8") as f:
        f.write(template(args.sender, args.receiver, n))
    print(path)
    return 0


def cmd_check(args):
    if not os.path.isfile(args.path):
        die(f"no such file: {args.path}")
    found = problems(args.path)
    for p in found:
        print(p)
    if found:
        print(f"INCOMPLETE {args.path}")
        return 1
    print(f"OK {args.path}")
    return 0


def cmd_move(args):
    src = args.path
    if not os.path.isfile(src):
        die(f"no such file: {src}")
    folder = os.path.dirname(os.path.abspath(src))
    if os.path.basename(folder) not in FOLDERS:
        die(f"{src} is not in a New/, Incomplete/, or Complete/ folder")
    with open(src, encoding="utf-8") as f:
        lines = f.read().splitlines()
    heads = [k for k, ln in enumerate(lines) if HEADING_RE.match(ln)]
    found = [k for k in heads if HEADING_RE.match(lines[k]).group(1).upper() == "STATUS"]
    if not found:
        die(f"{src} has no '## STATUS' section", 1)
    i = found[0]
    j = next((k for k in range(i + 1, len(lines)) if HEADING_RE.match(lines[k])), len(lines))
    lines[i + 1:j] = [args.status, ""]
    tmp = src + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    if args.status == "complete":
        found = problems(tmp)
        if found:
            os.remove(tmp)
            for p in found:
                print(p)
            print(f"REFUSED: packet is incomplete, not marked complete; left unchanged at {src}")
            return 1
    os.replace(tmp, src)
    dest_dir = os.path.join(os.path.dirname(folder), "Complete" if args.status == "complete" else "Incomplete")
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, os.path.basename(src))
    if os.path.abspath(dest) != os.path.abspath(src):
        if os.path.exists(dest):
            die(f"refusing to overwrite {dest}", 1)
        os.rename(src, dest)
    print(dest)
    return 0


def main():
    ap = argparse.ArgumentParser(description="Create, check, and move handoff packets.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new", help="write a new packet template and print its path")
    p.add_argument("--root", required=True)
    p.add_argument("--from", dest="sender", required=True)
    p.add_argument("--to", dest="receiver", required=True)
    p.set_defaults(func=cmd_new)
    p = sub.add_parser("check", help="exit 1 if any required field is missing or empty")
    p.add_argument("path")
    p.set_defaults(func=cmd_check)
    p = sub.add_parser("move", help="set STATUS and move to Complete/ or Incomplete/")
    p.add_argument("path")
    p.add_argument("--status", required=True, choices=STATUSES)
    p.set_defaults(func=cmd_move)
    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
