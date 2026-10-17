---
name: agenc-review
description: Use when an AgenC run (or any coding agent) has produced a change and you must decide whether to accept, fix, or reject it before it is merged or trusted.
---
# Review an AgenC change

An agent's change is a claim. Your review turns it into evidence or a rejection. Never merge on the agent's word.

Checked against AgenC 0.19.9. Run `agenc help <command>` to confirm flags.

## 1. Collect the inputs

You need four things before you start:
- The brief the agent got, with its allowed files and done command.
- The worktree or scratch dir it worked in.
- The base ref it started from.
- Its result file (`--output-format json`) and stderr log.

No brief means no scope fence. Write down what was allowed before you read the diff, not after.

## 2. Check the claim against the facts

```bash
python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print("exit",d["exitCode"]);print(d["finalMessage"])' result.json
```

- Exit code not `0`: the run failed, whatever `finalMessage` says. See [`agenc-retry`](../agenc-retry/SKILL.md).
- `finalMessage` says PASS but the exit code, the check output, or the diff disagrees: treat the whole run as untrusted.
- `finalMessage` does not match the output contract in the brief: that is a failure.
- `Partial result: stopped at the task budget` means unfinished work. Do not review it as done.

## 3. Run the helper

`review_check.py` (in this folder, Python standard library only) does the mechanical checks. It is read-only.

```bash
python3 review_check.py --worktree /tmp/wt-fix --base main \
  --allow 'src/parser.py' --allow 'tests/test_parser.py'
```

It reports, against the base ref, including uncommitted and untracked files:
- Changed files outside the `--allow` globs.
- Deleted or modified test files, and test files that lost assert lines.
- Added skip, xfail, or `.only` markers.
- Dependency and lock file changes.
- Snapshot and golden file changes.
- Stray `.agenc`, `.agents`, or nested `.git` dirs, empty ones included.
- Generated junk, debug leftovers, and secret-like strings in added lines.

Exit `0` means no findings. Exit `1` means findings. Exit `2` means a usage or git error. Every finding needs a reason to stay or it goes.

Rerun it after every fix. When the same problem shows up in review twice, add a pattern for it to the helper, prove the new pattern flags the past change, then stop reviewing for it by hand.

## 4. Re-run the done command yourself

```bash
cd /tmp/wt-fix && python3 -m pytest -q 2>&1 | tee /tmp/review-fix-tests.log
```

- Run the exact command from the brief, in the worktree, from a clean shell.
- Then exercise the change the way a user would: call the CLI, hit the endpoint, run the repro from the brief. Save the literal output.
- Green tests, a clean compile, or green CI alone are not proof. The saved output of the real thing is.

## 5. Read the full diff

```bash
git -C /tmp/wt-fix status --short
git -C /tmp/wt-fix diff main --stat
git -C /tmp/wt-fix diff main
```

Read every line. Check:
- **Scope.** Every file is in the brief. Unrequested refactors, renames, and reformatting count as scope creep.
- **Size.** The smallest change that fixes the root cause wins. Reject shims, one-caller wrappers, new layers "for later", and dead code. Prefer a deletion to an addition.
- **Root cause.** Reject guards that silence the error: broad `try/except`, `or default`, early returns that hide bad input.
- **Hardcoded outputs.** Special cases that match test inputs, returned constants, test-name checks, environment sniffing.
- **Dependencies.** Any new package needs a reason in the brief.
- **Secrets and leftovers.** Keys, tokens, debug prints, `breakpoint()`, commented-out code, TODOs the brief did not ask for.
- **Junk.** Logs, caches, build output, editor files, result files inside the tree.

## 6. Check the tests

- Deleted tests, new skip or xfail markers, loosened assertions (`==` to `in`, exact to approximate, fewer asserts), and rewritten snapshots are rejections unless the brief asked for them.
- New tests check behavior: inputs and outputs a user would see. Reject tests that assert on private helpers, call counts, or mock internals the change itself introduced.
- A new test must fail on the base code. Prove it:

```bash
git -C /tmp/wt-fix stash push -- src/   # keep the new tests, drop the fix
(cd /tmp/wt-fix && python3 -m pytest -q tests/test_parser.py) ; echo "expect nonzero: $?"
git -C /tmp/wt-fix stash pop
```

## 7. Get a read-only second opinion

For risky or large changes, run a second review with a different brief. Do not reuse the implementer's brief; ask it to attack the change. Run it in an empty scratch dir and paste the diff into the brief, so it needs no tools.

```bash
mkdir -p /tmp/review-fix && cd /tmp/review-fix
{ cat <<'BRIEF'
You are a reviewer, not an implementer. Review the diff below.
The change was meant to <one sentence>. Allowed files were <list>.
Do not edit files, run commands, or call plan-approval tools. Write your answer as your final message.
Find: bugs, missed edge cases, scope creep, weakened tests, hardcoded results, security issues.
Output: first line `VERDICT: ACCEPT|FIX|REJECT`, then at most 10 bullets, each `file:line - problem - fix`.
BRIEF
  echo '```diff'; git -C /tmp/wt-fix diff main; echo '```'; } > brief.md
agenc --provider <provider> --model <model> \
  --permission-mode default --task-max-calls 10 --deadline +600 \
  --output-format json -p "$(cat brief.md)" > /tmp/review-fix.json 2> /tmp/review-fix.err
```

- Headless runs have no approver. Edits and commands that need approval are denied, so a run in an empty dir stays read-only. Each denied tool still costs a call.
- `--permission-mode plan` also works, but in headless runs it tends to spend calls writing a plan file and asking to leave plan mode. If you use it, give it 15 or more calls.
- A second opinion finds problems. It does not replace steps 3 to 6.

## 8. Give a verdict

Write the verdict in this format:

```text
VERDICT: ACCEPT | FIX | REJECT
Run: <worktree> base=<ref> agenc exit=<code>
Evidence: <done command> -> <result>, log at <path>; helper exit=<code>
Reasons:
- <finding, file:line, why it matters>
Required changes (FIX only):
- <exact change>
```

- **ACCEPT.** Exit `0`, done command passes when you run it, helper findings all explained, diff in scope, tests check behavior.
- **FIX.** The approach is right and the remaining problems are small and clear. Fix them yourself, or re-brief with the exact changes listed. Then review again.
- **REJECT.** Wrong approach, fake success, weakened tests, hardcoded results, or out-of-scope edits you cannot cleanly drop. Reset the worktree and re-brief using [`agenc-retry`](../agenc-retry/SKILL.md). Up to 3 attempts per task in total; after the third, escalate to a human with the evidence.

Merge only after ACCEPT. Clean up stray `.agenc`, `.agents`, and nested `.git` dirs and the worktree after merge.
