---
name: agent-with-subagents
description: Use when designing an agent, or running a job, where a lead agent splits the work, dispatches subagents, then verifies and merges their results.
---
# Lead agent with subagents

A lead agent plans, splits, dispatches, verifies, merges, and reports. Subagents do bounded units of work. The worked example uses headless AgenC runs as subagents. The same pattern fits any harness with native subagents (Claude Code, Cursor, Codex, and others) or any CLI agent you can run from a shell.

AgenC flags checked against AgenC 0.19.9. AgenC has no built-in fan-out flag for print mode; you fan out by running separate processes. Run `agenc help <command>` to confirm flags.

## 1. Split or not

Split when:
- The job has parts that do not depend on each other.
- Each part has its own verifiable done condition.
- Parts touch different files, or produce read-only output.
- The lead's context would overflow doing it all.

Do not split when:
- The job is small or one tightly coupled change.
- Parts edit the same files or depend on each other's decisions.
- You cannot state a check for each part.
- Writing the briefs costs more than doing the work.

## 2. The lead's job

1. **Plan.** State the goal and the final acceptance check.
2. **Decompose.** Cut the job into independent units. Each unit has an owner, inputs, a scope fence, and a done condition.
3. **Dispatch.** One brief per unit. Caps on every run.
4. **Review.** Read every output and diff. Run every check.
5. **Merge.** One unit at a time. Re-run the checks after each merge.
6. **Report.** What was done, what was verified, what failed, real cost.

The lead never delegates:
- Final judgment on whether a unit is done.
- Merging into the main branch.
- Verification. A subagent's "tests pass" is a claim, not evidence.
- Anything irreversible: pushes, deploys, releases, sending messages.

## 3. Write subagent briefs

Each brief stands alone. The subagent has no access to the lead's conversation.

- **Goal.** One sentence.
- **Pointers.** Exact paths, symbols, commands.
- **Scope fence.** Files it may edit. Files it must not touch. No new dependencies unless allowed.
- **Done condition.** The command that must pass.
- **Output contract.** Where to write results and in what shape.

Output contract example:

```
Write your final message as JSON only:
{"unit": "<unit-id>", "status": "done|blocked|failed", "files_changed": ["..."], "checks": [{"cmd": "...", "passed": true}], "notes": "<= 3 sentences"}
```

Never put secrets in briefs.

## 4. Fan-out patterns

- **Parallel workers.** N independent units, one subagent each. Lead merges. Best for disjoint files or read-only analysis.
- **Pipeline.** Unit B starts from unit A's verified output. The lead checks each stage before handing it on.
- **N candidates, pick best.** Same brief to N subagents in separate dirs. The lead scores each against the done condition and keeps one.
- **Builder and reviewer.** A builder makes the change. A reviewer audits it read-only, with a different setup: a different provider or model you have configured, a different brief, or `--permission-mode plan`. The lead decides on the findings.

## 5. Isolation

- One worktree or directory per subagent: `git worktree add -b <branch> <dir>`.
- One output file per subagent, named by unit id, outside the worktree.
- No subagent writes shared state: no shared files, lockfiles, databases, or global config.
- Serialize merges. The lead merges one branch at a time and re-runs checks.
- Never run a subagent from `$HOME` or the main checkout.

## 6. Concurrency and budget

- Cap concurrency. Start at 2 or 3 parallel subagents.
- Cap each subagent: `--task-max-calls <n>`, `--deadline +<seconds>`, and optionally `--task-token-budget <tokens>`.
- Leave headroom on call caps. A cap that is too low ends the run with `Partial result: stopped at the task budget` and exit 1.
- For durable runs use `agenc run start ... --max-cost <usd>` as a hard USD cap.
- Set an overall budget: units times per-unit cap. Stop dispatching when you reach it.
- Track real cost from your provider's billing or usage endpoint before and after the job. AgenC's `tokenUsage.costUsd` is an estimate and can be far off.

## 7. Collect results

- Each AgenC run writes one JSON object with `--output-format json`: `type`, `exitCode`, `finalMessage`, `tokenUsage`, `events`.
- Record the process exit code in its own file.
- The lead parses `finalMessage` against the output contract. Malformed output is a failure.
- Then the lead runs the done condition itself in the subagent's worktree.

## 8. Failures and stalls

Exit codes: `0` ok, `1` failed (including a hit call cap), `2` denied or bad option, `3` review required, `4` empty, `5` deadline.

1. Every subagent has a deadline. A stall ends at the deadline with exit 5.
2. Read `finalMessage` and stderr. Find the cause.
3. Retry with a sharper, narrower brief. Three attempts total; if two fail on the same approach, the third changes it (split smaller, change the setup, or do it yourself).
4. After the third failure, stop and ask a human: goal, the three briefs, each failure's exit code and key error, what was ruled out, and the decision needed. Do not retry further.
5. Never retry past three. Never raise caps blindly.
6. Durable runs: `agenc run status <run-id>`, `agenc run cancel <run-id> --reason "<text>"`.
7. Background agents: `agenc agent list`, `agenc agent logs <id>`, `agenc agent stop <id>`.

## 9. Idempotency

- Dispatch is re-runnable. Key everything by unit id: worktree, branch, brief, output file.
- Skip a unit whose result already passed verification.
- Before a re-run, reset that unit's worktree and delete its old output files.
- Keep briefs in files so a re-run uses the same text.

## 10. Worked example: fan out 3 AgenC runs

```bash
#!/usr/bin/env bash
set -u
REPO=/path/to/repo
JOB=/tmp/job-$(date +%s)
UNITS=(parser-tests cli-help lint-fix)
mkdir -p "$JOB/briefs" "$JOB/out"

# Briefs: one self-contained file per unit, written by the lead.
# e.g. "$JOB/briefs/parser-tests.md"

for u in "${UNITS[@]}"; do
  wt="$JOB/wt-$u"
  [ -f "$JOB/out/$u.verified" ] && continue            # idempotent: skip verified units
  rm -rf "$wt"; git -C "$REPO" worktree prune
  git -C "$REPO" worktree add -f -B "sub/$u" "$wt" >/dev/null
  (
    cd "$wt" &&
    agenc --provider <provider> --model <model> \
      --permission-mode acceptEdits \
      --task-max-calls 30 --deadline +900 --deadline-reserve 60 \
      --output-format json -p "$(cat "$JOB/briefs/$u.md")" \
      > "$JOB/out/$u.json" 2> "$JOB/out/$u.err"
    echo $? > "$JOB/out/$u.exit"
  ) &
done
wait

# Lead checks every unit itself.
for u in "${UNITS[@]}"; do
  code=$(cat "$JOB/out/$u.exit" 2>/dev/null || echo missing)
  msg=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["finalMessage"])' "$JOB/out/$u.json" 2>/dev/null)
  echo "== $u exit=$code"
  echo "$msg" | head -20
  git -C "$JOB/wt-$u" status --short
  git -C "$JOB/wt-$u" diff --stat
  # Run the unit's done condition yourself, e.g.:
  # (cd "$JOB/wt-$u" && pytest -q) && touch "$JOB/out/$u.verified"
done
```

Then merge verified branches one at a time, re-running the full test suite after each. Remove worktrees with `git worktree remove <dir>` when done.

Other harnesses: replace the `agenc` call with your harness's subagent call or headless CLI. Keep the dirs, caps, deadlines, output files, and lead-side checks.

## 11. Agent definition template

Fill this in as the lead agent's own instructions.

```markdown
# Role
You are the lead agent for <job>. You plan, dispatch subagents, verify, merge, and report.
You do not push, deploy, or send anything without explicit approval.

# Inputs
- Repo or data: <path>
- Goal: <one sentence>
- Final acceptance check: <command>
- Budget: <max subagents>, <max concurrent>, <per-unit call cap>, <per-unit deadline>, <overall spend cap>

# Decomposition rules
- Split only into units that touch disjoint files or are read-only.
- Each unit has: id, goal, files allowed, files forbidden, done command, output contract.
- If two units need the same file, merge them into one unit or run them in sequence.
- Do small or coupled work yourself.

# Dispatch command
cd <unit worktree> && agenc --provider <provider> --model <model> \
  --permission-mode <plan|acceptEdits> --task-max-calls <n> --deadline +<seconds> \
  --output-format json -p "$(cat <brief file>)" > <out>/<id>.json 2> <out>/<id>.err

# Verification checklist (per unit)
- [ ] Exit code is 0.
- [ ] finalMessage matches the output contract.
- [ ] Diff stays inside the allowed files.
- [ ] Done command passes when I run it.
- [ ] No secrets, debug leftovers, or stray files.

# Failure policy
Up to three attempts, each with a sharper brief; the third changes the approach. Then stop and escalate to a human with a short note.

# Report format
- Goal and final check result.
- Per unit: id, status, verified (yes/no), files changed.
- Failures and what I did about them.
- Real cost from the provider's usage endpoint.
- Open items needing approval.
```
