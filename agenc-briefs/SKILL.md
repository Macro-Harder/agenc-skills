---
name: agenc-briefs
description: Use when writing the prompt (brief) for a headless AgenC run or any delegated coding agent, so it does the right thing the first time and returns a result you can check.
---
# Write AgenC briefs

The agent sees only the brief and the files in its directory. Anything you do not write down, it guesses.

Checked against AgenC 0.19.9. Run `agenc help <command>` to confirm flags.

## 1. Brief anatomy

Every brief has these parts, in this order:

1. **Goal.** One sentence. The outcome, not the steps.
2. **Context.** Exact file paths, functions, commands. Paste short snippets and literal error output; point to long ones.
3. **Data shape.** The types, signatures, schemas, or output format the work produces or must keep. Write this before any logic.
4. **Scope fence.** Files it may edit. Everything else is off limits.
5. **Constraints.** Smallest diff. No new dependencies. No wrappers, shims, or speculative layers. Do not delete, skip, or weaken tests.
6. **Done condition.** The exact command that must pass, plus anything a user would see.
7. **Commands.** Whether it may run shell commands. See section 2.
8. **Output contract.** The exact shape of the final message.

## 2. Rules that save a run

- **Keep briefs in files.** `briefs/<task>.md`. You can diff, rerun, and sharpen them. Pass them with `-p "$(cat briefs/<task>.md)"`.
- **Shape first.** Name the data shape before the logic. Ask for types where bad states cannot be represented: an enum instead of free strings, a required field instead of an optional one. Ask for input to be parsed and validated once, at the boundary.
- **Name the files.** "Fix the parser" makes it search. "Fix `parse_line()` in `src/parser.py`" does not.
- **One task per brief.** Two goals means split it (see [`agent-with-subagents`](../agent-with-subagents/SKILL.md)).
- **Root cause.** Ask for a reproduction first and a fix of the cause. Say that guards which hide the error do not count.
- **Headless runs have no approver.** A tool that needs approval is denied and still costs a call. In `--permission-mode acceptEdits`, tell the agent not to run shell commands and run the done command yourself. For read-only work, paste the input (a diff, a log excerpt) into the brief and tell it to answer in its final message without tools.
- **No secrets.** Never put keys, tokens, passwords, or private data in a brief. Pass credentials to tools through env vars, not the prompt.
- **Machine-checkable output.** A fixed first line such as `RESULT: PASS|FAIL`, or a JSON object with named fields. Prose is not a contract.

## 3. Anti-patterns

| Brief says | Problem | Write instead |
|---|---|---|
| "Improve the code" | No goal, no done | "Make `pytest tests/test_x.py` pass without editing tests" |
| "Fix the bug in auth" | No files, no repro | File, function, repro command, literal error |
| "Make tests pass" | Invites deleting or skipping tests | Add: "Do not delete, skip, or weaken tests" |
| "Clean up as needed" | Invites scope creep | List the files it may edit |
| "Use key sk-..." | Secret in a prompt and in logs | Credential in env; brief says which env var |
| Long chat history pasted in | Noise, cost, wrong focus | The facts it needs, nothing else |
| No output format | You cannot parse the result | Fixed first line or JSON schema |

## 4. Templates

Copy one, fill every `<...>`, delete lines that do not apply.

### Bug fix with repro

```text
Goal: Fix <symptom> in <function> in <file>.
Repro: `<command>` prints:
<literal output or error>
Expected: `<command>` prints <expected output>.
Data shape: <signature and types in and out>. Keep the signature.
Files you may edit: <file>, <test file>. Do not touch any other file.
Constraints: Fix the root cause with the smallest diff. No new dependencies. No wrappers or helpers. Do not delete, skip, or weaken tests. No try/except or default values that hide the error.
Done when: `<test command>` passes, and <test file> has one new test for the repro input that fails on the old code.
Commands: Shell commands need approval and this run has no approver, so do not run any. Edit the files and reason from the code; I will run the done command.
Output: Your final message is exactly one line: `RESULT: PASS <one-line summary>` or `RESULT: FAIL <reason>`.
```

### Add tests

```text
Goal: Add tests for <function or module> in <file>.
Behavior to cover: <list of cases: normal, edge, error>.
Files you may edit: <test file> only. Do not change code under test.
Constraints: Test behavior through the public interface: inputs and visible outputs. No mocks of internals. No sleeps. No network.
If a test exposes a bug, keep the test, mark nothing as skip, and report it.
Done when: `<test command>` runs the new tests. Every new test passes, or fails only because of a real bug you report.
Commands: <may run `<test command>` | do not run commands>.
Output: First line `RESULT: PASS <n> tests added` or `RESULT: FAIL <reason>`. Then one line per bug found: `BUG: <file>:<line> <what>`.
```

### Refactor with no behavior change

```text
Goal: <structural change, e.g. split <module> into <a> and <b>> with no behavior change.
Files you may edit: <list>.
Data shape: Public API stays identical: <list of public names and signatures>.
Constraints: Do not edit tests. No new features. No new dependencies. Delete code that becomes dead; do not leave shims or re-exports unless listed here: <list or none>.
Done when: `<test command>` passes with the test files unchanged, and `git diff --stat` touches only the listed files.
Commands: <...>.
Output: First line `RESULT: PASS` or `RESULT: FAIL <reason>`. Then a list of moved or renamed names, one per line: `old -> new`.
```

### Code review (read-only)

```text
Goal: Review the diff below. Do not edit anything.
Focus: correctness, missed edge cases, scope creep, weakened tests, hardcoded results, security.
Context: The change was meant to <one sentence>. Allowed files were <list>.
Commands: Do not run commands or call plan-approval tools. Write your answer as your final message.
Output: First line `VERDICT: ACCEPT|FIX|REJECT`. Then at most 10 bullets, each `<file>:<line> - <problem> - <fix>`. No praise, no summary.
<paste the diff here, fenced as diff>
```

Run it in an empty scratch dir. See [`agenc-review`](../agenc-review/SKILL.md) for the full procedure and flags.

### Summarize a large codebase or logs

```text
Goal: Answer <question> from <paths or log files>. Do not edit anything.
Scope: Read only <paths>. Ignore <vendor dirs, generated files>.
Commands: <may run read-only commands such as `rg`, `ls`, `wc` | do not run commands>.
Constraints: Cite evidence for every claim as `<file>:<line>` or a quoted log line. Say "unknown" instead of guessing.
Output: JSON only:
{"answer": "<2-5 sentences>", "evidence": [{"claim": "...", "where": "<file>:<line>"}], "unknowns": ["..."]}
```

### Docs update

```text
Goal: Update <doc file> to match the current behavior of <command, API, or module>.
Source of truth: <code paths or `--help` output pasted here>. The code wins over the old docs.
Files you may edit: <doc files>. Do not edit code.
Constraints: Keep the existing structure and tone. Every command and flag in the docs must exist in the source of truth. Remove docs for things that no longer exist.
Done when: Every example command in the doc runs as written. List any you could not check.
Output: First line `RESULT: PASS` or `RESULT: FAIL <reason>`. Then `UNVERIFIED: <command>` lines, if any.
```

### Migration or codemod

```text
Goal: Replace <old API or pattern> with <new API or pattern> across <paths>.
Rule: <old form> becomes <new form>. Example:
- before: <snippet>
- after:  <snippet>
Data shape: <new types or signatures>.
Files you may edit: files under <paths> that contain <pattern>. Nothing else.
Constraints: Prefer writing a script that does the rewrite and running it over hand-editing each file. Put the script at <path outside the repo or a named tools path>. Hand-edit only the cases the script cannot handle, and list them. No behavior changes.
Done when: `rg '<old pattern>' <paths>` returns nothing, and `<test command>` passes.
Commands: <...>.
Output: First line `RESULT: PASS <files changed>` or `RESULT: FAIL <reason>`. Then `MANUAL: <file>:<line>` for each hand edit.
```

## 5. Check the brief before you run it

- [ ] A stranger could do the task from this brief alone.
- [ ] Every file path exists.
- [ ] The done command runs and fails now, for the right reason.
- [ ] The output contract is something a script can parse.
- [ ] No secrets.

Run it with caps, as in [`agenc-offload`](../agenc-offload/SKILL.md). If it fails, sharpen it from the failure using [`agenc-retry`](../agenc-retry/SKILL.md).
