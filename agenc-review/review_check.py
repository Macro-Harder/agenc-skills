#!/usr/bin/env python3
"""Flag risky parts of an agent-made change before you trust it.

Usage:
  review_check.py --worktree DIR --base REF [--allow GLOB ...]

Compares the worktree (committed, staged, unstaged and untracked files)
against REF. Reports:
  - changed files outside the --allow globs
  - deleted test files, test files with removed lines, and lost assert lines
    (test files with added lines only are printed as a NOTE, not a finding)
  - added skip/xfail/only markers
  - dependency and lock file changes
  - snapshot or golden file changes
  - stray .agenc, .agents or nested .git dirs (empty ones included)
  - generated junk, debug leftovers and secret-like strings in added lines

Exit codes: 0 no findings, 1 findings, 2 usage or git error.
Python 3.8+ standard library only. Read-only: it never changes the worktree.
"""
import argparse
import fnmatch
import os
import re
import subprocess
import sys

TEST_PATH = re.compile(
    r"(^|/)(tests?|__tests__|spec|specs)/"
    r"|(^|/)test_[^/]*\.py$|_test\.(py|go|rb|exs?)$"
    r"|\.(test|spec)\.[cm]?[jt]sx?$|(Test|Tests|Spec)\.(java|kt|cs|swift)$"
)
SKIP_MARKER = re.compile(
    r"@pytest\.mark\.(skip|skipif|xfail)\b|pytest\.(skip|xfail)\("
    r"|@unittest\.(skip|skipIf|skipUnless|expectedFailure)\b|\.skipTest\("
    r"|\b(it|test|describe|context)\.(skip|only|todo)\(|\b(xit|xdescribe|xtest|fit|fdescribe)\("
    r"|\bt\.Skip(f|Now)?\(|#\[ignore\]|@(Disabled|Ignore)\b|\bskip\s*:\s*true\b"
)
ASSERT_LINE = re.compile(r"\bassert|\bexpect\(|\bself\.assert|\bt\.(Error|Fatal)|\bshould\b")
DEP_FILE = re.compile(
    r"(^|/)(requirements[^/]*\.(txt|in)|pyproject\.toml|setup\.(py|cfg)|Pipfile(\.lock)?"
    r"|poetry\.lock|uv\.lock|package(-lock)?\.json|yarn\.lock|pnpm-lock\.yaml|bun\.lockb?"
    r"|go\.(mod|sum)|Cargo\.(toml|lock)|Gemfile(\.lock)?|composer\.(json|lock)"
    r"|pom\.xml|build\.gradle(\.kts)?|[^/]*\.csproj|mix\.(exs|lock))$"
)
SNAPSHOT = re.compile(r"(^|/)(__snapshots__|snapshots?|golden|testdata/golden)/|\.(snap|golden)$")
JUNK = re.compile(
    r"(^|/)(__pycache__|node_modules|\.pytest_cache|\.mypy_cache|\.ruff_cache|\.tox|dist|build|coverage|htmlcov)(/|$)"
    r"|\.(pyc|pyo|log|orig|rej|bak|swp|tmp)$|(^|/)(\.DS_Store|nohup\.out|\.coverage)$"
)
DEBUG = re.compile(
    r"\bbreakpoint\(\)|\bimport pdb\b|\bpdb\.set_trace\(|\bdebugger;|\bconsole\.log\(|\bdbg!\("
    r"|\bprint\((\"|')?(debug|DEBUG|here|HERE|XXX)|\bTODO\b|\bFIXME\b|\bHACK\b"
)
SECRET = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|\bAKIA[0-9A-Z]{16}\b|\bgh[pousr]_[A-Za-z0-9]{30,}\b"
    r"|\bsk-[A-Za-z0-9_-]{20,}\b|\bxox[abpr]-[A-Za-z0-9-]{10,}\b"
    r"|(?i:(api[_-]?key|secret|token|passw(or)?d)\s*[:=]\s*['\"][^'\"\s]{8,}['\"])"
)
STRAY_DIRS = {".agenc", ".agents", ".git"}
SKIP_WALK = {"node_modules", ".venv", "venv"}


def git(wt, *args, check=True):
    p = subprocess.run(["git", "-C", wt, *args], capture_output=True, text=True)
    if check and p.returncode != 0:
        sys.exit(f"review_check: git {' '.join(args)} failed: {p.stderr.strip()}")
    return p.stdout


def changed_files(wt, base):
    """Return {path: status} for tracked changes plus untracked files."""
    out = {}
    for line in git(wt, "diff", "--name-status", "--no-renames", base, "--").splitlines():
        status, _, path = line.partition("\t")
        if path:
            out[path] = status[0]
    for path in git(wt, "ls-files", "--others", "--exclude-standard").splitlines():
        out[path] = "?"
    return out


def diff_lines(wt, base, files):
    """Return {path: (added_lines, removed_lines)}."""
    res = {p: ([], []) for p in files}
    cur = None
    for line in git(wt, "diff", "-U0", "--no-renames", "--no-color", base, "--").splitlines():
        if line.startswith("+++ "):
            cur = line[6:] if line.startswith("+++ b/") else None
            res.setdefault(cur, ([], [])) if cur else None
        elif line.startswith("--- "):
            continue
        elif cur and line.startswith("+"):
            res[cur][0].append(line[1:])
        elif cur and line.startswith("-"):
            res[cur][1].append(line[1:])
    for path, status in files.items():
        if status == "?":
            try:
                with open(os.path.join(wt, path), encoding="utf-8", errors="replace") as f:
                    res[path] = (f.read().splitlines(), [])
            except (IsADirectoryError, FileNotFoundError):
                pass
    return res


def stray_dirs(wt, base):
    tracked = set(git(wt, "ls-tree", "-r", "-d", "--name-only", base).splitlines())
    hits = []
    for root, dirs, _ in os.walk(wt):
        rel_root = os.path.relpath(root, wt)
        for d in list(dirs):
            rel = os.path.normpath(os.path.join(rel_root, d))
            if rel == ".git" or d in SKIP_WALK:
                dirs.remove(d)
                continue
            if d in STRAY_DIRS:
                dirs.remove(d)
                if rel not in tracked:
                    hits.append(rel + "/")
    if os.path.isfile(os.path.join(wt, ".git")) is False and not os.path.isdir(os.path.join(wt, ".git")):
        hits.append("(worktree has no .git)")
    return sorted(hits)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--worktree", required=True, help="worktree or checkout to inspect")
    ap.add_argument("--base", required=True, help="git ref the change started from")
    ap.add_argument("--allow", action="append", default=[],
                    help="glob of files the brief allowed (repeatable); none means skip the scope check")
    a = ap.parse_args()
    wt = os.path.abspath(a.worktree)
    if not os.path.isdir(wt):
        print(f"review_check: no such dir: {wt}", file=sys.stderr)
        return 2
    git(wt, "rev-parse", "--verify", "--quiet", a.base + "^{commit}")

    files = changed_files(wt, a.base)
    lines = diff_lines(wt, a.base, files)
    findings = {}
    notes = []

    def add(section, msg):
        findings.setdefault(section, []).append(msg)

    for path, status in sorted(files.items()):
        added, removed = lines.get(path, ([], []))
        if a.allow and not any(fnmatch.fnmatch(path, g) for g in a.allow):
            add("OUT OF SCOPE", f"{status} {path}")
        if TEST_PATH.search(path):
            if status == "D":
                add("TEST FILES", f"deleted {path}")
            elif status == "M" and not removed:
                notes.append(f"test file {path}: lines added only")
            elif status == "M":
                ra = sum(1 for l in removed if ASSERT_LINE.search(l))
                aa = sum(1 for l in added if ASSERT_LINE.search(l))
                note = f" (assert lines -{ra} +{aa}, check for weakened checks)" if ra > aa else ""
                add("TEST FILES", f"modified {path}: {len(removed)} line(s) removed{note}")
        for l in added:
            if SKIP_MARKER.search(l):
                add("SKIP/XFAIL MARKERS", f"{path}: {l.strip()[:120]}")
            if SECRET.search(l):
                add("SECRET-LIKE STRINGS", f"{path}: (line redacted, inspect by hand)")
            elif DEBUG.search(l):
                add("DEBUG LEFTOVERS", f"{path}: {l.strip()[:120]}")
        if DEP_FILE.search(path):
            add("DEPENDENCY FILES", f"{status} {path}")
        if SNAPSHOT.search(path):
            add("SNAPSHOT/GOLDEN FILES", f"{status} {path}")
        if JUNK.search(path):
            add("GENERATED JUNK", f"{status} {path}")
    for d in stray_dirs(wt, a.base):
        add("STRAY DIRS", d)

    print(f"review_check: {wt} vs {a.base}: {len(files)} changed file(s)")
    for path, status in sorted(files.items()):
        print(f"  {status} {path}")
    for n in notes:
        print(f"NOTE: {n}")
    if not findings:
        print("FINDINGS: none")
        return 0
    print(f"FINDINGS: {sum(len(v) for v in findings.values())}")
    for section, msgs in findings.items():
        print(f"[{section}]")
        for m in msgs:
            print(f"  {m}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
