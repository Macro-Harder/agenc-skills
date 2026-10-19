#!/usr/bin/env python3
"""kit.py - manage agent kit folder (skills/, agents/, requests/, INDEX.md)"""

from __future__ import annotations
import argparse
import datetime
import os
import re
import sys
import tempfile
from pathlib import Path


def parse_index(kit_dir: Path):
    index_path = kit_dir / "INDEX.md"
    if not index_path.is_file():
        return [], ""
    content = index_path.read_text(encoding="utf-8")
    rows = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            if len(cells) == 4:
                if cells[0].lower() not in ("type", "---") and cells[1] != "name":
                    rows.append({
                        "type": cells[0].lower(),
                        "name": cells[1],
                        "status": cells[2].lower(),
                        "date": cells[3],
                    })
    return rows, content


def has_required_parts(text: str) -> bool:
    checks = [
        "**What it is.**",
        "**What it does.**",
        "**Why it's needed:**",
    ]
    return all(check in text for check in checks)


def scan_kit(kit_dir: Path):
    skills = {}
    agents = {}
    requests = {}

    for subdir, store in [("skills", skills), ("agents", agents)]:
        d = kit_dir / subdir
        if d.is_dir():
            for item in d.iterdir():
                if item.is_dir():
                    blurb = item / "BLURB.md"
                    store[item.name] = blurb.is_file()

    req_dir = kit_dir / "requests"
    if req_dir.is_dir():
        for f in req_dir.glob("*.md"):
            requests[f.stem] = f

    return skills, agents, requests


def do_list(kit_dir: Path):
    rows, _ = parse_index(kit_dir)
    print(f"{len(rows)} INDEX row(s) in {kit_dir / 'INDEX.md'}")
    for row in rows:
        print(f"| {row['type']} | {row['name']} | {row['status']} | {row['date']} |")

    skills, agents, requests = scan_kit(kit_dir)
    issues = []
    indexed = {(r["type"], r["name"]) for r in rows}

    for name, has_blurb in skills.items():
        if ("skill", name) not in indexed:
            issues.append(f"skill {name} on disk missing from INDEX" + ("" if has_blurb else " (and missing BLURB.md)"))
    for name, has_blurb in agents.items():
        if ("agent", name) not in indexed:
            issues.append(f"agent {name} on disk missing from INDEX" + ("" if has_blurb else " (and missing BLURB.md)"))
    for name in requests:
        if ("request", name) not in indexed:
            issues.append(f"request {name} on disk missing from INDEX")

    for r in rows:
        t = r["type"]
        name = r["name"]
        if t == "skill":
            if name not in skills:
                issues.append(f"INDEX skill {name} has no folder on disk")
            elif not skills[name]:
                issues.append(f"skill {name} folder missing BLURB.md")
        elif t == "agent":
            if name not in agents:
                issues.append(f"INDEX agent {name} has no folder on disk")
            elif not agents[name]:
                issues.append(f"agent {name} folder missing BLURB.md")
        elif t == "request":
            if name not in requests:
                issues.append(f"INDEX request {name} has no file on disk")
            else:
                try:
                    content = requests[name].read_text(encoding="utf-8")
                    if not has_required_parts(content):
                        issues.append(f"request {name} missing required parts")
                except Exception:
                    issues.append(f"request {name} unreadable")

    if issues:
        print(f"DRIFT: {len(issues)} issue(s)")
        for issue in issues:
            print("  " + issue)
        sys.exit(2)
    print(f"OK: {len(skills)} skill(s), {len(agents)} agent(s), {len(requests)} request(s); INDEX matches disk")
    sys.exit(0)


def do_show(kit_dir: Path, name: str):
    # request
    req_path = kit_dir / "requests" / f"{name}.md"
    if req_path.is_file():
        print(req_path.read_text(encoding="utf-8"), end="")
        return

    # skill
    skill_path = kit_dir / "skills" / name / "BLURB.md"
    if skill_path.is_file():
        print(skill_path.read_text(encoding="utf-8"), end="")
        return

    # agent
    agent_path = kit_dir / "agents" / name / "BLURB.md"
    if agent_path.is_file():
        print(agent_path.read_text(encoding="utf-8"), end="")
        return

    print(f"No item found for {name}", file=sys.stderr)
    sys.exit(1)


def do_request(kit_dir: Path, name: str, what: str, does: str, why: str, idea: str | None, dry_run: bool):
    if not re.match(r"^[a-z0-9][a-z0-9-]{1,60}$", name):
        print("Invalid NAME: must match ^[a-z0-9][a-z0-9-]{1,60}$", file=sys.stderr)
        sys.exit(1)

    req_dir = kit_dir / "requests"
    req_path = req_dir / f"{name}.md"

    if req_path.exists():
        print(f"requests/{name}.md already exists", file=sys.stderr)
        sys.exit(1)

    content = f"# {name}\n\n"
    content += f"**What it is.**\n{what}\n\n"
    content += f"**What it does.**\n{does}\n\n"
    content += f"**Why it's needed:**\n{why}\n\n"
    if idea:
        content += f"**One idea to improve it**\n{idea}\n"

    date = datetime.date.today().isoformat()
    new_row = f"| request | {name} | requested | {date} |"

    if dry_run:
        print(f"Would create: {req_path}")
        print(content)
        print(f"Would append to INDEX.md: {new_row}")
        return

    req_dir.mkdir(parents=True, exist_ok=True)
    req_path.write_text(content, encoding="utf-8")

    index_path = kit_dir / "INDEX.md"
    if not index_path.exists():
        header = "| type | name | status | date |\n|---|---|---|---|\n"
        index_path.write_text(header + new_row + "\n", encoding="utf-8")
    else:
        idx_content = index_path.read_text(encoding="utf-8")
        if not idx_content.endswith("\n"):
            idx_content += "\n"
        idx_content += new_row + "\n"
        index_path.write_text(idx_content, encoding="utf-8")

    print(f"Created requests/{name}.md and appended to INDEX.md")


def do_status(kit_dir: Path, name: str, new_status: str, dry_run: bool):
    allowed = {"active", "retired", "requested", "granted"}
    if new_status not in allowed:
        print(f"Invalid status '{new_status}'. Allowed: {', '.join(sorted(allowed))}", file=sys.stderr)
        sys.exit(1)

    index_path = kit_dir / "INDEX.md"
    if not index_path.is_file():
        print("INDEX.md not found", file=sys.stderr)
        sys.exit(1)

    content = index_path.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)

    found = False
    old_status = None
    new_lines = []
    name_pattern = re.escape(name)

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|") and re.search(rf"\|\s*{name_pattern}\s*\|", stripped):
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            if len(cells) == 4 and cells[1] == name:
                old_status = cells[2]
                type_ = cells[0]
                date = cells[3]
                new_line = f"| {type_} | {name} | {new_status} | {date} |\n"
                new_lines.append(new_line)
                found = True
                continue
        new_lines.append(line)

    if not found:
        print(f"{name} not found in INDEX.md", file=sys.stderr)
        sys.exit(1)

    if dry_run:
        print(f"Would change: {old_status} -> {new_status}")
        return

    # Atomic rewrite
    fd, tmp_path = tempfile.mkstemp(dir=kit_dir, suffix=".md", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("".join(new_lines))
        os.replace(tmp_path, index_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise

    print(f"{old_status} -> {new_status}")


def do_add(kit_dir: Path, kind: str, name: str, dry_run: bool):
    """Index a skill/agent folder you already copied into the kit (it must carry BLURB.md)."""
    folder = kit_dir / (kind + "s") / name
    blurb = folder / "BLURB.md"
    if not blurb.is_file():
        print(f"{blurb} missing: copy the folder in and write its four-part BLURB.md first", file=sys.stderr)
        sys.exit(1)
    if not has_required_parts(blurb.read_text(encoding="utf-8")):
        print(f"{blurb} lacks a required part (What it is / What it does / Why it's needed)", file=sys.stderr)
        sys.exit(1)
    rows, _ = parse_index(kit_dir)
    if any(r["type"] == kind and r["name"] == name for r in rows):
        print(f"{kind} {name} already in INDEX.md; use status to change it", file=sys.stderr)
        sys.exit(1)
    import datetime as _dt
    row = f"| {kind} | {name} | active | {_dt.date.today().isoformat()} |"
    if dry_run:
        print(f"Would append to INDEX.md: {row}")
        return
    idx = kit_dir / "INDEX.md"
    text = idx.read_text(encoding="utf-8") if idx.exists() else "# Index\n\n| type | name | status | date |\n|---|---|---|---|\n"
    if not text.endswith("\n"):
        text += "\n"
    with open(idx, "w" if not idx.exists() else "a", encoding="utf-8") as f:
        f.write(text if not idx.exists() else ("" if idx.read_text(encoding="utf-8").endswith("\n") else "\n"))
        f.write(row + "\n")
    print(f"Indexed: {row}")


def main():
    parser = argparse.ArgumentParser(prog="kit.py")
    parser.add_argument(
        "--kit",
        default=os.environ.get("AGENT_KIT") or ".",
        help="Kit directory (default: $AGENT_KIT or current dir)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="List INDEX and check for drift")

    show_p = subparsers.add_parser("show", help="Show blurb for NAME")
    show_p.add_argument("name")

    req_p = subparsers.add_parser("request", help="Create a new request")
    req_p.add_argument("name")
    req_p.add_argument("--what", required=True)
    req_p.add_argument("--does", required=True)
    req_p.add_argument("--why", required=True)
    req_p.add_argument("--idea")
    req_p.add_argument("--dry-run", action="store_true")

    stat_p = subparsers.add_parser("status", help="Change status of NAME in INDEX")
    stat_p.add_argument("name")
    stat_p.add_argument("new_status")
    stat_p.add_argument("--dry-run", action="store_true")

    add_p = subparsers.add_parser("add", help="Index a skill/agent folder already in the kit")
    add_p.add_argument("kind", choices=["skill", "agent"])
    add_p.add_argument("name")
    add_p.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    kit_dir = Path(args.kit).resolve()

    if args.command == "list":
        do_list(kit_dir)
    elif args.command == "show":
        do_show(kit_dir, args.name)
    elif args.command == "request":
        do_request(kit_dir, args.name, args.what, args.does, args.why, args.idea, args.dry_run)
    elif args.command == "status":
        do_status(kit_dir, args.name, args.new_status, args.dry_run)
    elif args.command == "add":
        do_add(kit_dir, args.kind, args.name, args.dry_run)


if __name__ == "__main__":
    main()
