---
name: agenc-offload
description: Use when you want to save your own context and tokens by handing heavy, self-contained work (codegen, refactors, test runs, long reads, summaries, reviews) to a headless AgenC run and then verifying the result yourself.
---
# Offload work to AgenC

You coordinate. AgenC does the heavy lifting in a separate headless process. You own every result it returns.

Checked against AgenC 0.19.9. Flags change; run `agenc help` and `agenc help <command>` when something misbehaves.

## 1. Offload or do it inline

Offload when the task:
- Is self-contained and fits in one written brief.
- Would flood your context (reading many files, long logs, large diffs).
- Has a checkable done condition (tests pass, file exists, output matches a format).
- Can run while you do something else.

Do it inline when:
- It is a few lines or one quick command.
- It needs the conversation history or judgment calls you cannot write down.
- Explaining it takes longer than doing it.
- It touches secrets, production, deploys, or pushes.

## 2. Write a self-contained brief

The offloaded agent sees only the brief and the files in its directory. Include:

1. **Goal.** One sentence. What done looks like.
2. **Pointers.** Exact file paths, functions, commands. Paste short snippets; point to long ones.
3. **Constraints.** What not to touch. Style rules. No new dependencies unless allowed.
4. **Success criteria.** The command that must pass, or the check you will run.
5. **Output format.** Exact shape of the final answer: a file path, a JSON schema, or a fixed first line such as `RESULT: PASS|FAIL`.

Keep the brief in a file so you can rerun and refine it:

```bash
cat > brief.md <<'BRIEF'
Goal: Add input validation to parse_config() in src/config.py.
Files: src/config.py, tests/test_config.py.
Constraints: Do not change public function signatures. No new dependencies.
Success: `pytest tests/test_config.py` passes. Add at least 3 new tests.
Output: Final message is exactly one line: `RESULT: PASS` or `RESULT: FAIL <reason>`.
BRIEF
```

Never put secrets, tokens, or private data in a brief.

## 3. Run it

Rules:
- **Options go before `-p`.** Anything after the prompt starts is treated as prompt text. A trailing flag is silently ignored.
- **Run from a project or scratch directory, never `$HOME`.** Launching from `$HOME` fails with `[sandbox_required_unavailable]`.
- **Use a scratch dir or git worktree for edits.** Never point an edit run at your main checkout.
- **Always cap.** `--task-max-calls` caps model calls. `--deadline +<seconds>` stops the run (exit 5). `--deadline-reserve <seconds>` leaves time to wrap up.
- **Pick the permission mode.** `--permission-mode plan` for read-only analysis and reviews. `--permission-mode acceptEdits` for scoped edits.

Read-only task:

```bash
cd "$(mktemp -d)" && cp -r /path/to/inputs .
agenc --provider <provider> --model <model> \
  --permission-mode plan --task-max-calls 15 --deadline +600 \
  --output-format json -p "$(cat /path/to/brief.md)" > result.json 2> err.log
echo "exit=$?"
```

Edit task in a worktree:

```bash
git -C /path/to/repo worktree add -b offload/validate /tmp/offload-validate
cd /tmp/offload-validate
agenc --provider <provider> --model <model> \
  --permission-mode acceptEdits --task-max-calls 30 --deadline +900 \
  --output-format json -p "$(cat /path/to/brief.md)" > /tmp/offload-validate.json 2> /tmp/offload-validate.err
```

Write result files outside the worktree so they never end up in the diff.

Set call caps with headroom. Even a trivial task uses several model calls. A cap that is too low ends the run with `Partial result: stopped at the task budget` and exit 1. Raise the cap once; do not keep raising it.

Token caps: `--budget eco|balanced|max` or `--task-token-budget <tokens>`. If the provider rejects requests as too large for your allowance, set `AGENC_MAX_OUTPUT_TOKENS=4000` in the environment.

Durable, verified-change runs with a hard USD cap:

```bash
agenc run start --goal-file brief.md --cwd /tmp/offload-validate \
  --model <model> --permission-mode acceptEdits --max-cost 1.00 \
  --verify "tests=pytest -q" --follow
agenc run status <run-id>
agenc run result <run-id>
agenc run cancel <run-id> --reason "stalled"
```

`agenc run pause <run-id>` and `agenc run resume <run-id>` keep the original cost cap and deadline.

Background agents: `agenc agent start --unattended-allow <tools> "<objective>"`, then `agenc agent list`, `agenc agent logs <id>`, `agenc agent stop <id>`. Grant only the tools the task needs.

## 4. Capture results

- `--output-format json` prints one JSON object: `type`, `exitCode`, `finalMessage`, `tokenUsage`, `events`.
- `--output-format text` prints only the final message. `stream-json` streams events.
- Redirect stdout to a file. Keep stderr in a separate log.
- Parse `finalMessage` for your output contract:

```bash
python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print(d["exitCode"]);print(d["finalMessage"])' result.json
```

## 5. Run several in parallel

- One directory or worktree per run. Never two runs in the same tree.
- One output file per run, named after the task.
- No run writes a shared file. Merge results yourself, one at a time.
- Start with 2 or 3 concurrent runs. Add more only after they finish cleanly.

```bash
for t in parse-tests cli-docs lint-fix; do
  ( cd "/tmp/wt-$t" && agenc --provider <provider> --model <model> \
      --permission-mode acceptEdits --task-max-calls 30 --deadline +900 \
      --output-format json -p "$(cat "/tmp/briefs/$t.md")" \
      > "/tmp/out-$t.json" 2> "/tmp/out-$t.err"; echo $? > "/tmp/out-$t.exit" ) &
done
wait
```

## 6. Verify before you trust

The offloaded agent can be wrong, partial, or confidently mistaken. You own every diff.

- Read the full diff: `git -C <worktree> diff` and `git -C <worktree> status`.
- Run the success command yourself. Do not accept "tests pass" as evidence.
- Check scope. Reject edits outside the files you named.
- Check the output contract. Missing or malformed output is a failure.
- Delete stray empty `.git`, `.agenc`, or `.agents` dirs it may leave in a scratch dir.
- Merge only after all checks pass.

## 7. Track real cost

AgenC's `tokenUsage.costUsd` is an estimate and can be off by orders of magnitude. Do not report it.

- Read usage from your provider's billing or usage endpoint before and after the run.
- Usage can lag a minute or more. Wait before the second read.
- Print only usage numbers. Never print the key.

```bash
curl -s "$PROVIDER_USAGE_URL" -H "Authorization: Bearer $PROVIDER_API_KEY" | jq '.data.usage'
```

## 8. Handle failures

Exit codes: `0` ok, `1` failed (including a hit call cap), `2` denied or bad option, `3` review required, `4` empty result, `5` deadline.

1. Read `finalMessage` and stderr. Find the real cause.
2. Exit 2: fix the flag or permission. Check that options come before `-p`.
3. Call cap with 0 tokens used: the first call failed. Fix the error; do not raise the cap.
4. Wrong or partial work: retry with a sharper brief. Quote the failure. Narrow the scope. Name the exact files. Restate the output format. Reset the scratch dir or worktree first.
5. Three attempts total. If two attempts fail on the same approach, the third must change the approach, not just the wording.
6. Third failure: stop and ask a human. Write a short note: the goal, the three briefs, each exit code and key error, what you ruled out, and the decision or input you need. Do not retry further.

Never retry past three. Never raise caps blindly.

## 9. Safety

- No secrets, tokens, or credentials in briefs or result files.
- Keep the sandbox on. `--bypass-approvals` still runs commands in the OS sandbox. Never use `--dangerously-bypass-approvals-and-sandbox`.
- No deploys, pushes, releases, or infrastructure changes through the offloaded agent. You push after review.
- Scratch dirs and worktrees only. Never your main checkout or `$HOME`.
- Always set `--task-max-calls` and `--deadline` for unattended runs.
