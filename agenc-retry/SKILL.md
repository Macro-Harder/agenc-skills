---
name: agenc-retry
description: Use when an AgenC run failed, hit a cap, or returned bad work, to find the cause, decide whether to retry, split, or do it yourself, and sharpen the brief without looping.
---
# Triage a failed AgenC run

A failed run is data. Read it before you spend another call. Each task gets at most 3 attempts in total; then a human decides.

Checked against AgenC 0.19.9. Run `agenc help <command>` to confirm flags.

## 1. Gather the evidence

```bash
echo "exit=$(cat run.exit)"            # or the $? you saved
tail -20 run.err
python3 - run.json <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except (OSError, ValueError):
    sys.exit("no JSON result: the run failed before it started; read stderr")
print("exitCode", d["exitCode"]); print(d["finalMessage"][:800])
print("tokens", d.get("tokenUsage", {}).get("totalTokens"))
for e in d.get("events", []):
    ev = e.get("params", {}).get("event")
    if isinstance(ev, dict) and ev.get("type") == "tool_call_completed":
        r = str(ev.get("payload", {}).get("result", ""))
        if "Permission denied" in r:
            print("DENIED", ev["payload"].get("toolName"), r[:120])
PY
```

Reproduce before you change anything. Confirm the failure is in the run, not in your check: run the done command on the base code and on the result.

## 2. Map the failure to a cause

| Signal | Cause | Fix |
|---|---|---|
| Exit `0`, but your check fails | Bad work or a fake success claim | Sharpen the brief (section 4). Quote the check output. |
| Exit `1`, `Partial result: stopped at the task budget`, `reached its N model-call limit`, tokens > 0 | Call cap too low, or the agent wandered | Look at what the calls did. Wasted calls: fix the brief. Real work: raise the cap once. |
| Same, with 0 tokens | The first call failed | Read stderr. Fix the error. Do not raise the cap. |
| Exit `1`, empty JSON, stderr names a flag conflict (for example `--bypass-approvals conflicts with --permission-mode acceptEdits`) | Bad flag combination | Pass one of them. |
| Exit `1`, empty JSON, `project is not trusted` | Bypass flags need the directory trusted interactively first | Drop the bypass flag, or trust the directory once by hand in a terminal. |
| `DENIED` lines in events: `Permission denied ... non-interactive one-shot: no approver` | Headless runs cannot answer approval prompts; each denied tool still costs a call | Tell the brief which tools not to call, or run the command yourself. |
| Exit `1` at the call cap, events show plan files and repeated plan-exit requests | `--permission-mode plan` in a headless run | Paste the input into the brief, run in an empty scratch dir with `--permission-mode default`, or give plan mode 15 or more calls. |
| Exit `2` | Denied action or bad option | Check flag spelling with `agenc help`. Check that every option comes before `-p`. |
| Exit `3` | Review required | The run stopped for approval. Review what it wants; do not bypass blindly. |
| Exit `4` | Empty result | Brief had no clear deliverable, or the output contract was unclear. Restate the contract. |
| Exit `5` | Deadline | Read how far it got. Split the task, or raise `--deadline` once if it was close. |
| `[sandbox_required_unavailable]` | Launched from `$HOME` | `cd` into a project or scratch dir. |
| `request is too large for the current allowance` | Output token request over the account allowance | Set `AGENC_MAX_OUTPUT_TOKENS=4000` (or lower). |
| Ran on the wrong model, or a 404 | `--provider`/`--model` placed after `-p` | Move every option before `-p`. |
| Diff outside scope, deleted or skipped tests | Brief too loose | Run [`agenc-review`](../agenc-review/SKILL.md). Add the scope fence and test rules to the brief. |

AgenC's `costUsd` is an estimate. It is never the cause of a failure and never evidence of spend; see [`agenc-spend-guard`](../agenc-spend-guard/SKILL.md).

## 3. Retry, split, or do it yourself

Retry when:
- The cause is clear and fixable in the brief or flags.
- The done condition is still right.

Split when:
- The run ran out of calls or time doing real work.
- The task has independent parts (see [`agent-with-subagents`](../agent-with-subagents/SKILL.md)).

Do it yourself when:
- The fix is a few lines and you already know it.
- The task needs judgment you cannot write down.
- The failure is in your environment, not the brief.

## 4. Sharpen the brief from the failure

Each new attempt changes the brief based on what went wrong. Rewording the same brief is not a new attempt.

1. **Quote the failure.** Paste the literal error, failing test output, or review finding.
2. **Narrow the scope.** Fewer files, one function, one behavior.
3. **Name the files.** Exact paths and function names, not descriptions.
4. **Restate the contract.** The exact final-message format and done command.
5. **Say what not to do.** "Do not edit tests." "Do not call plan-approval tools." "Do not run shell commands."

```text
Previous attempt failed: `pytest tests/test_parser.py::test_empty` raised
  ValueError: empty line at src/parser.py:42
Fix only parse_line() in src/parser.py. Empty input returns []. Do not edit tests.
Output: exactly one line, `RESULT: PASS` or `RESULT: FAIL <reason>`.
```

Keep every brief version: `briefs/<task>.1.md`, `.2.md`, `.3.md`. The escalation note needs them.

## 5. Reset before every retry

A retry starts from the base, not from the last attempt's mess.

```bash
git -C /tmp/wt-task reset --hard <base-ref>
git -C /tmp/wt-task clean -fdx
```

Or remove the worktree and add a fresh one. Save anything you want from the failed attempt (diff, logs) outside the worktree first. Use a new result file per attempt: `task.2.json`, `task.2.err`.

## 6. Three attempts, then escalate

- **Attempt 1.** The original brief.
- **Attempt 2.** Sharpened from attempt 1's failure.
- **Attempt 3.** If attempts 1 and 2 failed for the same reason, the premise is wrong. Change the approach, not the wording: a different design, a smaller unit, different files, or a different done condition.
- **After attempt 3 fails, stop.** No fourth run. Write an escalation note and hand it to a human.

Never raise caps blindly. Raise a cap at most once, and only when the calls did real work. Never put retries in a loop.

Escalation note:

```text
ESCALATION: <task id>
Goal: <one sentence>
Attempts:
1. brief briefs/<task>.1.md -> exit <code>: <key error, one line>
2. brief briefs/<task>.2.md (changed: <what>) -> exit <code>: <key error>
3. brief briefs/<task>.3.md (new approach: <what>) -> exit <code>: <key error>
Ruled out: <causes you checked and eliminated>
Evidence: <paths to result files, logs, diffs>
Needed from you: <one specific decision or input>
```

Ask for one specific decision. "Please help" is not a question.

## 7. Before asking a human

Do not wait on a human for anything you can check or undo yourself: rerunning the done command, reading logs, resetting a worktree, trying a narrower brief within the 3 attempts. Stop and ask only for irreversible actions, missing access or credentials, product or policy decisions, and the post-attempt-3 escalation.
