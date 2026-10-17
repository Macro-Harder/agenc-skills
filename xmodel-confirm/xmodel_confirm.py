#!/usr/bin/env python3
"""Cross-model bug confirmation: re-check audit findings with a different model via AgenC.

Usage:
  xmodel_confirm.py --findings findings.json --target CODE_DIR --original-model ID \
      --model CHECK_MODEL_ID --out OUT_DIR [--reasoning-effort high] [--max-tokens 4000]

Per finding: a blind audit (run once, findings hidden) plus a judge call decides
REDISCOVERED; otherwise a targeted CONFIRM/REFUTE check decides CONFIRMED_WHEN_SHOWN,
DISPUTED or INCONCLUSIVE. Writes OUT_DIR/results.json and OUT_DIR/results.md.
Every model call is an `agenc -p` run (provider openrouter, read-only sandbox, cwd =
target). Requires `agenc` on PATH; OPENROUTER_API_KEY in env is used only to read
real key usage before and after. The target is never written to.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

def safe_int(val: Any) -> int:
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0

def escape_md(text: str) -> str:
    return str(text or "").replace("|", "\\|")

def get_openrouter_usage(api_key: Optional[str]) -> Optional[float]:
    if not api_key:
        return None
    try:
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/key",
            headers={"Authorization": f"Bearer {api_key}"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            usage = data.get("data", {}).get("usage") or data.get("usage")
            if isinstance(usage, (int, float)):
                return float(usage)
            if isinstance(usage, dict):
                for k in ["total_cost", "cost", "total_cost_usd", "usd"]:
                    if k in usage:
                        return float(usage[k])
            return None
    except Exception:
        return None

def run_agenc(model: str, prompt: str, cwd: Path, max_tokens: int, timeout: int, effort: Optional[str],
              config_file: Optional[Path] = None, task_max_calls: int = 4, deadline: Optional[str] = None) -> Dict[str, Any]:
    agenc_bin = shutil.which("agenc")
    if not agenc_bin:
        print("Error: agenc not found in PATH", file=sys.stderr)
        sys.exit(2)
    argv = [agenc_bin, "--permission-mode", "default", "--output-format", "json"]
    if config_file:
        argv += ["--config", str(config_file)]
    argv += ["--task-max-calls", str(task_max_calls)]
    if deadline:
        argv += ["--deadline", deadline]
    argv += ["-p", "--provider", "openrouter", "--model", model, "--", prompt]
    env = os.environ.copy()
    env["AGENC_MAX_OUTPUT_TOKENS"] = str(max_tokens)
    if effort:
        env["AGENC_EFFORT_LEVEL"] = effort
    start = time.time()
    try:
        proc = subprocess.run(
            argv, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=timeout + 60
        )
        exit_code = proc.returncode
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip() if proc.stderr else ""
    except subprocess.TimeoutExpired:
        return {"exit_code": 124, "seconds": timeout, "text": "", "agenc_estimate_usd": None,
                "input_tokens": 0, "output_tokens": 0, "error": "timeout"}
    text = ""
    agenc_cost = None
    input_tokens = 0
    output_tokens = 0
    parsed = None
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    parsed = json.loads(line)
                    break
                except:
                    continue
    if parsed and isinstance(parsed, dict):
        if parsed.get("type") == "result" or "finalMessage" in parsed:
            text = parsed.get("finalMessage", "") or ""
            token_usage = parsed.get("tokenUsage", {}) or {}
            if isinstance(token_usage, dict):
                try:
                    agenc_cost = float(token_usage.get("costUsd") or 0)
                except:
                    agenc_cost = None
                input_tokens = safe_int(token_usage.get("inputTokens", 0))
                output_tokens = safe_int(token_usage.get("outputTokens", 0))
        else:
            text = str(parsed)
    else:
        text = stdout
    error = None
    if exit_code != 0 or not text.strip():
        error = (text[:300] if text else (stderr or "no output")[-400:])
    return {
        "exit_code": exit_code,
        "seconds": round(time.time() - start, 2),
        "text": text,
        "agenc_estimate_usd": agenc_cost,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "error": error
    }

def execute_call(model: str, prompt: str, cwd: Path, max_tokens: int, timeout: int,
                 effort: Optional[str], purpose: str, api_key: Optional[str], cost_settle: int = 5,
                 config_file: Optional[Path] = None, task_max_calls: int = 4, deadline: Optional[str] = None) -> Dict[str, Any]:
    before = get_openrouter_usage(api_key)
    res = run_agenc(model, prompt, cwd, max_tokens, timeout, effort, config_file, task_max_calls, deadline)
    time.sleep(cost_settle)
    after = get_openrouter_usage(api_key)
    delta = None
    if before is not None and after is not None:
        delta = round(after - before, 8)
    res["purpose"] = purpose
    res["model"] = model
    res["key_usage_delta_usd"] = delta
    if api_key and res.get("error"):
        res["error"] = str(res["error"]).replace(api_key, "[REDACTED]")
    return res

def extract_json(text: str) -> Dict[str, Any]:
    text = re.sub(r'```(?:json)?\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'```\s*$', '', text)
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except:
            pass
    return {}

def parse_model_findings(text: str) -> List[Dict[str, Any]]:
    data = extract_json(text)
    if isinstance(data.get("findings"), list):
        return data["findings"]
    return []

def parse_findings_input(path: Path) -> List[Dict[str, Any]]:
    content = path.read_text(encoding="utf-8", errors="replace")
    try:
        data = json.loads(content)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("findings"), list):
            return data["findings"]
    except:
        pass
    findings = []
    current = None
    for line in content.splitlines():
        if line.startswith("## "):
            if current:
                findings.append(current)
            m = re.match(r"##\s*([^:]+):\s*(.+)", line)
            if m:
                current = {
                    "id": m.group(1).strip(),
                    "title": m.group(2).strip(),
                    "description": "",
                    "severity": "medium",
                    "file": "",
                    "line": 0,
                    "repro": None
                }
        elif current:
            ls = line.strip()
            if ls.lower().startswith("- severity:"):
                current["severity"] = ls.split(":", 1)[1].strip()
            elif ls.lower().startswith("- file:"):
                current["file"] = ls.split(":", 1)[1].strip()
            elif ls.lower().startswith("- line:"):
                current["line"] = safe_int(ls.split(":", 1)[1].strip())
            elif ls.lower().startswith("repro:") or ls.lower().startswith("- repro:"):
                current["repro"] = ls.split(":", 1)[1].strip()
            elif not ls.startswith("- "):
                current["description"] += line + "\n"
    if current:
        findings.append(current)
    for f in findings:
        f.setdefault("description", "").strip()
        f.setdefault("severity", "medium")
        f.setdefault("repro", None)
        f["line"] = safe_int(f.get("line", 0))
    return findings

def normalize_file(f: str, target: Path) -> str:
    if not f:
        return ""
    f = str(f).strip()
    if f.startswith("./"):
        f = f[2:]
    try:
        p = Path(f)
        if p.is_absolute():
            try:
                return str(p.relative_to(target.resolve()))
            except ValueError:
                return p.name
        return str(p)
    except:
        return f

def find_candidates(orig: Dict, blind: List[Dict], window: int, target: Path) -> List[Dict]:
    of = normalize_file(orig.get("file", ""), target)
    ol = safe_int(orig.get("line", 0))
    cands = []
    for b in blind:
        bf = normalize_file(b.get("file", ""), target)
        bl = safe_int(b.get("line", 0))
        if (bf == of or Path(bf).name == Path(of).name) and abs(bl - ol) <= window:
            cands.append(b)
    return cands

def get_code_excerpt(target: Path, rel_file: str, line: int, window: int, bundle: str) -> Tuple[str, str]:
    try:
        base = target if target.is_file() else target
        p = base / rel_file if rel_file else base
        if p.is_file():
            content = p.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines(keepends=True)
            start = max(0, line - window - 1)
            end = min(len(lines), line + window)
            out = [f"  {i+1}| {lines[i].rstrip()}" for i in range(start, end)]
            return "\n".join(out), ""
        else:
            first = "\n".join(bundle.splitlines()[:200])
            numbered = "\n".join(f"  {i+1}| {ln}" for i, ln in enumerate(first.splitlines()))
            return numbered, "Note: specified file not found under target; using first 200 lines of the code bundle instead."
    except Exception:
        first = "\n".join(bundle.splitlines()[:200])
        numbered = "\n".join(f"  {i+1}| {ln}" for i, ln in enumerate(first.splitlines()))
        return numbered, "Note: error reading file; using first 200 lines of the code bundle instead."

def parse_judge(text: str) -> Dict[str, Any]:
    lines = [l for l in text.strip().splitlines() if l.strip()]
    matched = False
    decided = False
    reason = ""
    cand = None
    current_label = None
    buffer = []
    for line in lines:
        cleaned = re.sub(r'[*#`]', '', line).strip()
        upper_clean = cleaned.upper()
        if not decided:
            if upper_clean == "NO_MATCH":
                matched = False
                decided = True
                current_label = None
                continue
            elif upper_clean == "MATCH":
                matched = True
                decided = True
                current_label = None
                continue
        if upper_clean.startswith("REASON:"):
            current_label = "reason"
            buffer = [cleaned.split(":", 1)[1].strip()]
            continue
        elif upper_clean.startswith("CANDIDATE:"):
            cand = safe_int(cleaned.split(":", 1)[1].strip())
            if current_label == "reason":
                reason = "\n".join(buffer)[:1500]
            current_label = None
            continue
        if current_label == "reason":
            buffer.append(cleaned)
            if len("\n".join(buffer)) > 1500:
                break
    if current_label == "reason":
        reason = "\n".join(buffer)[:1500]
    return {"matched": matched, "reason": reason, "candidate": cand}

def parse_targeted(text: str) -> Dict[str, Any]:
    lines = text.strip().splitlines()
    ans = "UNSURE"
    decided = False
    out = {"reason": "", "detail": ""}
    current_label = None
    buffer: List[str] = []

    def flush() -> None:
        if current_label in out and buffer:
            out[current_label] = "\n".join(buffer)[:1500].strip()

    for line in lines:
        cleaned = re.sub(r'[*#`]', '', line).strip()
        upper_clean = cleaned.upper()
        if not decided:
            if upper_clean == "CONFIRM":
                ans = "CONFIRM"
                decided = True
                current_label = None
                continue
            elif upper_clean == "REFUTE":
                ans = "REFUTE"
                decided = True
                current_label = None
                continue
            elif upper_clean == "UNSURE":
                ans = "UNSURE"
                decided = True
                current_label = None
                continue
        if upper_clean.startswith("REASON:"):
            flush()
            current_label = "reason"
            buffer = [cleaned.split(":", 1)[1].strip()]
            continue
        elif upper_clean.startswith("REPRO:"):
            flush()
            current_label = "detail"
            buffer = [cleaned.split(":", 1)[1].strip()]
            continue
        elif upper_clean.startswith("COUNTER:"):
            flush()
            current_label = "detail"
            buffer = [cleaned.split(":", 1)[1].strip()]
            continue
        if current_label in ("reason", "detail"):
            buffer.append(cleaned)
    flush()
    return {"answer": ans, "reason": out["reason"], "detail": out["detail"]}

def read_bundle(target: Path, max_chars: int) -> str:
    parts = []
    total = 0
    base = target if target.is_dir() else target.parent
    if target.is_file():
        files = [target]
    else:
        files = []
        for p in sorted(target.rglob("*")):
            if not p.is_file():
                continue
            if any(x in p.parts for x in [".git", "__pycache__"]):
                continue
            if p.suffix in {".pyc", ".pyo", ".so", ".dll", ".exe", ".bin"}:
                continue
            try:
                if p.stat().st_size > 200 * 1024:
                    continue
                files.append(p)
            except:
                continue
    for p in files:
        try:
            rel = p.relative_to(base)
            content = p.read_text(encoding="utf-8", errors="replace")
            numbered = "\n".join(f"  {i+1}| {ln}" for i, ln in enumerate(content.splitlines()))
            entry = f"### FILE: {rel}\n{numbered}\n"
            if total + len(entry) > max_chars:
                parts.append("... [code bundle truncated]")
                break
            parts.append(entry)
            total += len(entry)
        except:
            continue
    return "\n".join(parts)

def main():
    parser = argparse.ArgumentParser(description="Cross-check audit findings with a different model via AgenC.")
    parser.add_argument("--findings", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--original-model", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--judge-model")
    parser.add_argument("--perspective", default="security and correctness bug audit")
    parser.add_argument("--scope", default="all files under target")
    parser.add_argument("--line-window", type=int, default=10)
    parser.add_argument("--reasoning-effort", choices=["minimal", "low", "medium", "high", "xhigh", "max"])
    parser.add_argument("--agent-timeout", type=int, default=900)
    parser.add_argument("--max-tokens", type=int, default=4000)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--max-code-chars", type=int, default=60000)
    parser.add_argument("--cost-settle-seconds", type=int, default=5)
    parser.add_argument("--final-settle-seconds", type=int, default=60)
    parser.add_argument("--task-max-calls", type=int, default=4)
    args = parser.parse_args()

    if args.model == args.original_model:
        print("Error: --model must differ from --original-model", file=sys.stderr)
        sys.exit(2)

    target = args.target.resolve()
    out_dir = args.out.resolve()
    if out_dir == target or target in out_dir.parents:
        print("Error: --out resolves inside --target", file=sys.stderr)
        sys.exit(2)

    cwd = target if target.is_dir() else target.parent
    home = Path.home()
    if cwd == home or cwd in home.parents:
        print("Error: refusing to run with cwd at or above home", file=sys.stderr)
        sys.exit(2)

    api_key = os.environ.get("OPENROUTER_API_KEY")
    effort = args.reasoning_effort
    max_tokens = args.max_tokens
    timeout = args.agent_timeout
    window = args.line_window
    judge_model = args.judge_model or args.model
    cost_settle = args.cost_settle_seconds
    final_settle = args.final_settle_seconds
    task_max_calls = args.task_max_calls

    findings = parse_findings_input(args.findings)
    for f in findings:
        f["file"] = normalize_file(f.get("file", ""), target)
        f["line"] = safe_int(f.get("line", 0))

    if not target.exists():
        print(f"Error: target not found: {target}", file=sys.stderr)
        sys.exit(2)
    if not findings:
        print("Error: no findings parsed from --findings", file=sys.stderr)
        sys.exit(2)
    # the prompt is passed as one argv string; Linux caps a single arg at 128 KiB
    bundle = read_bundle(target, min(args.max_code_chars, 110000))

    calls: List[Dict] = []
    start_usage = get_openrouter_usage(api_key)
    temp_dir = Path(tempfile.mkdtemp(prefix="xmodel-confirm-"))
    import atexit
    atexit.register(shutil.rmtree, temp_dir, True)
    config_file = temp_dir / "config.toml"
    config_file.write_text('config_version = 2\nsandbox_mode = "read-only"\n', encoding="utf-8")

    # 1. Blind rediscovery
    blind_prompt = (
        "All code you need is included below. Do not use tools, do not read or modify any files. Answer only in the requested format.\n\n"
        f"You are an independent code auditor.\n"
        f"Perspective: {args.perspective}\n"
        f"Scope: {args.scope}\n\n"
        f"CODE BUNDLE:\n{bundle}\n\n"
        f"Output ONLY a JSON object with key 'findings' containing a list of objects with keys: "
        f"file, line (int), title, description, severity."
    )
    blind_call = execute_call(args.model, blind_prompt, cwd, max_tokens, timeout, effort, "blind_rediscovery", api_key,
                              cost_settle, config_file, task_max_calls, f"+{timeout}")
    calls.append(blind_call)
    blind_findings: List[Dict] = []
    blind_error = None
    if blind_call.get("error") or blind_call.get("exit_code", 0) != 0:
        blind_error = blind_call.get("error") or f"exit {blind_call.get('exit_code')}"
    else:
        blind_findings = parse_model_findings(blind_call.get("text", ""))
        for b in blind_findings:
            if isinstance(b, dict):
                b["file"] = normalize_file(b.get("file", ""), target)
                b["line"] = safe_int(b.get("line", 0))

    processed = []
    for orig in findings:
        blind_match: Dict[str, Any] = {"matched": False, "candidate": None, "reason": ""}
        if blind_error:
            blind = "error"
        else:
            cands = find_candidates(orig, blind_findings, window, target)
            if cands:
                judge_prompt = (
                    "All code you need is included below. Do not use tools, do not read or modify any files. Answer only in the requested format.\n\n"
                    f"Original finding:\n"
                    f"ID: {orig.get('id')}\nTitle: {orig.get('title')}\nFile: {orig.get('file')}\n"
                    f"Line: {orig.get('line')}\nSeverity: {orig.get('severity')}\n"
                    f"Description: {orig.get('description')}\n\n"
                    f"Candidates:\n"
                )
                for i, c in enumerate(cands):
                    judge_prompt += (
                        f"\n[{i}] File: {c.get('file')} Line: {c.get('line')}\n"
                        f"Title: {c.get('title')}\nDescription: {c.get('description')}\n"
                    )
                judge_prompt += (
                    "\nReply with first line exactly MATCH or NO_MATCH.\n"
                    "Then REASON: ...\nIf MATCH also CANDIDATE: <index>\n"
                    "Same root cause required."
                )
                jcall = execute_call(judge_model, judge_prompt, cwd, max_tokens, timeout, effort, "judge", api_key,
                                     cost_settle, config_file, task_max_calls, f"+{timeout}")
                calls.append(jcall)
                if jcall.get("error"):
                    blind = "error"
                    blind_match["reason"] = "judge error: " + str(jcall["error"])[:300]
                else:
                    blind_match = parse_judge(jcall.get("text", ""))
                    blind = "MATCH" if blind_match.get("matched") else "NO_MATCH"
                    if blind == "MATCH" and blind_match.get("candidate") is not None and 0 <= blind_match["candidate"] < len(cands):
                        blind_match["candidate_finding"] = cands[blind_match["candidate"]]
            else:
                blind = "no candidates"
        # Targeted check
        excerpt, note = get_code_excerpt(target, orig.get("file", ""), orig.get("line", 0), 40, bundle)
        tgt_prompt = (
            "All code you need is included below. Do not use tools, do not read or modify any files. Answer only in the requested format.\n\n"
            f"You are performing a {args.perspective}. Be skeptical.\n\n"
            f"Finding:\nID: {orig.get('id')}\nTitle: {orig.get('title')}\n"
            f"File: {orig.get('file')}\nLine: {orig.get('line')}\n"
            f"Severity: {orig.get('severity')}\nDescription: {orig.get('description')}\n"
            f"{'Repro: ' + str(orig.get('repro')) if orig.get('repro') else ''}\n\n"
            f"CODE EXCERPT:\n{excerpt}\n"
        )
        if note:
            tgt_prompt += f"\n{note}\n\n"
        tgt_prompt += (
            "Reply with first line exactly CONFIRM, REFUTE or UNSURE.\n"
            "Then REASON: ...\nREPRO: ... or COUNTER: ..."
        )
        tcall = execute_call(args.model, tgt_prompt, cwd, max_tokens, timeout, effort, "targeted", api_key,
                             cost_settle, config_file, task_max_calls, f"+{timeout}")
        calls.append(tcall)
        if tcall.get("error"):
            targeted = {"answer": "ERROR", "reason": str(tcall["error"])[:300], "detail": ""}
        else:
            targeted = parse_targeted(tcall.get("text", ""))

        if blind == "MATCH":
            verdict = "REDISCOVERED"
        elif targeted.get("answer") == "CONFIRM":
            verdict = "CONFIRMED_WHEN_SHOWN"
        elif targeted.get("answer") == "REFUTE":
            verdict = "DISPUTED"
        else:
            verdict = "INCONCLUSIVE"

        processed.append({
            "id": orig.get("id"),
            "title": orig.get("title"),
            "file": orig.get("file"),
            "line": orig.get("line"),
            "severity": orig.get("severity"),
            "verdict": verdict,
            "blind": blind,
            "blind_match": blind_match,
            "targeted": targeted
        })

    time.sleep(final_settle)
    end_usage = get_openrouter_usage(api_key)
    if start_usage is not None and end_usage is not None:
        key_total = round(end_usage - start_usage, 8)
        cost_complete = True
    else:
        key_total = sum((c.get("key_usage_delta_usd") or 0) for c in calls if c.get("key_usage_delta_usd") is not None)
        cost_complete = False
    agenc_total = sum((c.get("agenc_estimate_usd") or 0) for c in calls)

    results = {
        "original_model": args.original_model,
        "check_model": args.model,
        "judge_model": judge_model,
        "target": str(target),
        "perspective": args.perspective,
        "blind_findings": blind_findings,
        "blind_error": blind_error,
        "findings": processed,
        "calls": calls,
        "agenc_estimate_total_usd": round(agenc_total, 8),
        "key_usage_delta_total_usd": key_total,
        "cost_complete": cost_complete,
        "cost_note": "key_usage_delta is the real OpenRouter key spend measured around each run and may include concurrent jobs on the same key; agenc_estimate is AgenC's own estimate",
        "note": "Model agreement is evidence, not proof. A failing reproduction test outranks model agreement. DISPUTED findings need a human or test review before being dropped."
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    md_lines = [
        "| id | severity | file:line | title | verdict | blind | targeted |",
        "|----|----------|-----------|-------|---------|-------|----------|"
    ]
    for f in processed:
        md_lines.append(
            f"| {escape_md(str(f.get('id','')))} | {escape_md(str(f.get('severity','')))} | "
            f"{escape_md(str(f.get('file','')))}:{f.get('line',0)} | {escape_md(str(f.get('title','')))} | "
            f"{escape_md(str(f.get('verdict','')))} | {escape_md(str(f.get('blind','')))} | "
            f"{escape_md(str(f.get('targeted',{}).get('answer','')))} |"
        )
    md_lines.append("")
    md_lines.append(f"Real cost (OpenRouter key usage delta over the whole run, may include concurrent jobs on the same key): ${results['key_usage_delta_total_usd']:.6f}")
    md_lines.append(f"AgenC estimate (not real cost): ${results['agenc_estimate_total_usd']:.6f} over {len(calls)} agent runs")
    md_lines.append("")
    md_lines.append(results["note"])
    md = "\n".join(md_lines)
    (out_dir / "results.md").write_text(md, encoding="utf-8")
    print(md)
    shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    main()
