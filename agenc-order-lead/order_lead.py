#!/usr/bin/env python3
"""order_lead.py - hand orders to a running AgenC lead via job docs (stdlib only)."""

from __future__ import annotations
import argparse
import datetime
import fnmatch
import glob
import hashlib
import json
import os
import sys


def main():
    parser = argparse.ArgumentParser(description="Order lead via job docs")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # send
    send_p = subparsers.add_parser("send")
    send_p.add_argument("--job-dir", action="append", required=True)
    send_p.add_argument("--from", dest="sender", required=True)
    send_p.add_argument("--title", required=True)
    send_p.add_argument("--sessions", nargs="*", default=[],
                        help="rollout globs; their current sizes are saved so confirm scans only what the lead wrote after the order")
    send_p.add_argument("--receipt-dir", default=os.path.expanduser("~/.local/state/agenc-order"))
    send_p.add_argument("--body", default=None)
    send_p.add_argument("--body-file", default=None)
    send_p.add_argument("--dry-run", action="store_true")

    # confirm
    conf_p = subparsers.add_parser("confirm")
    conf_p.add_argument("--tag", required=True)
    conf_p.add_argument("--sessions", nargs="+", required=True)
    conf_p.add_argument("--since", default=None)
    conf_p.add_argument("--receipt-dir", default=os.path.expanduser("~/.local/state/agenc-order"))

    args = parser.parse_args()

    if args.command == "send":
        do_send(args)
    elif args.command == "confirm":
        do_confirm(args)


def do_send(args):
    if args.body is None and args.body_file is None:
        print("Error: either --body or --body-file is required", file=sys.stderr)
        sys.exit(1)

    if args.body is not None:
        body = args.body
    else:
        try:
            with open(args.body_file, "r", encoding="utf-8") as f:
                body = f.read()
        except Exception as e:
            print(f"Error reading --body-file: {e}", file=sys.stderr)
            sys.exit(1)

    now = datetime.datetime.now().astimezone()
    tag = now.strftime("ORDER-%Y%m%d-%H%M%S")
    tz_abbr = now.tzname() or "LOCAL"
    inbox_time = now.strftime("%Y-%m-%d ") + now.strftime("%I:%M %p").lstrip("0")
    dec_time = now.strftime("%Y-%m-%d %H:%M")

    from_name = args.sender
    title = args.title

    inbox_append = f"\n## {inbox_time} {tz_abbr} — {from_name}: {title} [{tag}]\n{body}\n"
    dec_append = f"- {dec_time} {tz_abbr} ({from_name}, order): {title} [{tag}]; full text in INBOX.md\n"

    job_dirs = args.job_dir

    # Pre-write checks
    inbox_hashes = {}
    dec_sizes = {}
    for jdir in job_dirs:
        ip = os.path.join(jdir, "INBOX.md")
        dp = os.path.join(jdir, "DECISIONS.md")
        if not os.path.isfile(ip):
            print(f"ERROR: missing {ip}", file=sys.stderr)
            sys.exit(1)
        if not os.path.isfile(dp):
            print(f"ERROR: missing {dp}", file=sys.stderr)
            sys.exit(1)

        with open(ip, "rb") as f:
            inbox_hashes[jdir] = hashlib.sha256(f.read()).hexdigest()
        dec_sizes[jdir] = os.path.getsize(dp)

    if len(set(inbox_hashes.values())) > 1:
        print("WARNING: INBOX.md copies differ (sha256)")
    if len(set(dec_sizes.values())) > 1:
        print("WARNING: DECISIONS.md copies differ in size")

    if args.dry_run:
        for jdir in job_dirs:
            ip = os.path.join(jdir, "INBOX.md")
            dp = os.path.join(jdir, "DECISIONS.md")
            print(f"Would append to {ip}:")
            print(inbox_append)
            print(f"Would append to {dp}:")
            print(dec_append)
        return

    print(f"Tag: {tag}")
    failed = False

    for jdir in job_dirs:
        ip = os.path.join(jdir, "INBOX.md")
        dp = os.path.join(jdir, "DECISIONS.md")

        try:
            with open(ip, "a", encoding="utf-8") as f:
                f.write(inbox_append)
            with open(dp, "a", encoding="utf-8") as f:
                f.write(dec_append)
        except Exception as e:
            print(f"Error appending to {jdir}: {e}", file=sys.stderr)
            failed = True
            continue

        # Re-read and verify
        try:
            with open(ip, "r", encoding="utf-8") as f:
                ic = f.read()
            with open(dp, "r", encoding="utf-8") as f:
                dc = f.read()

            i_ok = tag in ic
            d_ok = tag in dc
            print(f"{jdir} INBOX: {'OK' if i_ok else 'FAIL'}")
            print(f"{jdir} DECISIONS: {'OK' if d_ok else 'FAIL'}")
            failed = failed or not (i_ok and d_ok)
        except Exception as e:
            print(f"Error verifying {jdir}: {e}")
            failed = True

    offsets = {}
    for pattern in args.sessions:
        for f in glob.glob(pattern):
            if f.endswith(".jsonl") and os.path.isfile(f):
                offsets[f] = os.path.getsize(f)
    os.makedirs(args.receipt_dir, exist_ok=True)
    rpath = os.path.join(args.receipt_dir, tag + ".json")
    with open(rpath, "w", encoding="utf-8") as f:
        json.dump({"tag": tag, "title": title, "job_dirs": job_dirs, "session_offsets": offsets}, f, indent=2)
    print(f"Receipt: {rpath} ({len(offsets)} session offsets)")
    print(f"Next: order_lead.py confirm --tag {tag} --sessions '<rollout glob>'")
    if failed:
        print("FAIL: the order did not land in every copy; fix before relying on it", file=sys.stderr)
        sys.exit(1)


def do_confirm(args):
    tag = args.tag
    try:
        time_part = tag[6:] if tag.startswith("ORDER-") else tag
        tag_dt = datetime.datetime.strptime(time_part, "%Y%m%d-%H%M%S")
        tag_ts = tag_dt.timestamp()
    except Exception:
        print("Invalid --tag format (expected ORDER-YYYYMMDD-HHMMSS)", file=sys.stderr)
        sys.exit(1)

    since_ts = None
    if args.since:
        try:
            s = args.since
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            since_dt = datetime.datetime.fromisoformat(s)
            since_ts = since_dt.timestamp()
        except Exception:
            print("Warning: could not parse --since, ignoring", file=sys.stderr)

    # Expand globs and filter by mtime
    file_set = set()
    for pattern in args.sessions:
        for f in glob.glob(pattern):
            if os.path.isfile(f):
                file_set.add(f)

    relevant = []
    for fpath in sorted(file_set):
        if not fpath.endswith(".jsonl"):
            continue
        try:
            mtime = os.path.getmtime(fpath)
            if mtime >= tag_ts and (since_ts is None or mtime >= since_ts):
                relevant.append(fpath)
        except OSError:
            continue

    rpath = os.path.join(args.receipt_dir, tag + ".json")
    offsets = {}
    if os.path.isfile(rpath):
        with open(rpath, encoding="utf-8") as f:
            offsets = json.load(f).get("session_offsets", {})
        # sessions that existed at send time are scanned from their saved offset,
        # even if their mtime filter would have dropped them
        for fpath in offsets:
            if os.path.isfile(fpath) and fpath not in relevant and any(fnmatch.fnmatch(fpath, p) for p in args.sessions):
                relevant.append(fpath)
    print(f"Scanning {len(relevant)} session file(s); receipt {'found' if offsets else 'not found: INBOX reads below may predate the order'}")
    tag_seen = False
    inbox_read_after = False

    for filepath in relevant:
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                start = offsets.get(filepath, 0)
                if start:
                    f.seek(start)
                for lineno, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if data.get("type") != "event_msg":
                        continue

                    pld = data.get("payload", {})
                    msg = pld.get("msg", {})
                    mtype = msg.get("type")
                    if mtype not in ("tool_call_completed", "tool_call_started", "agent_message"):
                        continue

                    inner = msg.get("payload", {})
                    context = json.dumps(inner, ensure_ascii=False)[:200]
                    full_text = json.dumps(data, ensure_ascii=False)

                    if tag in full_text:
                        k = full_text.find(tag)
                        context = full_text[max(0, k - 80):k + 120]
                        print(f"TAG  {os.path.basename(filepath)} +{lineno} {mtype}: {context}")
                        tag_seen = True

                    if mtype == "tool_call_started":
                        args_val = str(inner.get("args", ""))
                        if "INBOX.md" in args_val:
                            print(f"READ {os.path.basename(filepath)} +{lineno} {mtype}: {args_val[:160]}")
                            inbox_read_after = True

        except Exception:
            continue

    if tag_seen:
        print(f"CONFIRMED: the lead saw {tag}")
        sys.exit(0)
    elif inbox_read_after:
        print(f"READ-NOT-SEEN: INBOX.md was read but {tag} not seen in output (truncated read, or read predates order)")
        sys.exit(3)
    else:
        print(f"NOT YET: no sign the lead has read {tag}; check again after its next unit")
        sys.exit(4)


if __name__ == "__main__":
    main()
