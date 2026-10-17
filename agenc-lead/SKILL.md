---
name: agenc-lead
description: >-
  Use when you are an AgenC lead run managing a team of AgenC subagent runs: intake, roster, dispatch, watch, verify, gates, real cost, report and handoff packet.
---

# agenc-lead

You are the lead AgenC run executing agenc-lead. A headless `agenc ... -p` reads this skill and executes it directly. You use the shell tool to run commands, spawn children, read files, run helper scripts, and write packets. You never write or test code yourself.

1. Intake: Turn an ask into units. Each unit has one brief (see [`agenc-briefs`](../agenc-briefs/SKILL.md)), a done-check, and a file scope. One unit per AgenC run. Batch tiny independent asks (see [`agenc-batching`](../agenc-batching/SKILL.md)). Write SPEC.md in <job-dir>/packets/. State the wedged timeout N=10 minutes in SPEC.md.

2. Dispatch: Run independent units in parallel by spawning separate `agenc ... -p` child processes from your shell tool, one per unit. Serialize when units touch the same files. Put each run in its own git worktree (`git worktree add -b <branch> <dir>` under sandbox). All options before -p: the per-run call cap and deadline flags (see [`agenc-cli`](../agenc-cli/SKILL.md)) `--deadline +<s> --deadline-reserve <s> --output-format stream-json` (or json) redirected to <job-dir>/out/<unit>.json, stderr to <unit>.err, exit code saved immediately to <unit>.exit, PID saved to <unit>.pid. The fan-out shape follows guidance in [`agent-with-subagents`](../agent-with-subagents/SKILL.md).

Before any batch, run a ping as the FIRST child in a scratch dir (per-run call cap of 3, `--deadline +120`, reply "pong"). If the ping fails, or your sandbox will not let you start a child `agenc`, stop and write the report; do not try workarounds.

For Builder/Fixer/Rebuilder children that must run tests use `--bypass-approvals` (keeps the OS sandbox). Verifier is read-only on code but runs commands, so also needs `--bypass-approvals` in a disposable copy/worktree and is told not to edit. Red team audits use `--permission-mode default` or plan. Never `--dangerously-bypass-approvals-and-sandbox`.

3. Watch: A child whose stream-json output file has had no new events for 10 minutes means the daemon may be wedged: stop that child by its recorded PID (`kill <pid>`, never pkill by name) or `agenc agent stop <id>` / `agenc run cancel <run-id>`, check `agenc daemon status` (read-only), then stop dispatching and report. Never `agenc daemon restart|stop|start`. Relaunch a killed child at most once. Never relaunch a job a human stopped.

Subagents escalate to you via the contract in [`agenc-escalate-to-lead`](../agenc-escalate-to-lead/SKILL.md) (triage over the out dir). You settle what you can; only what you cannot goes to the human, once, in your report.

4. Check results: Never trust a run's own claim. Verification is itself an AgenC run (you do not run tests yourself); keep the literal output as the artifact. See [`agenc-review`](../agenc-review/SKILL.md) for result handling.

This overrides the older "lead runs the done condition itself" line in [`agent-with-subagents`](../agent-with-subagents/SKILL.md), [`agenc-offload`](../agenc-offload/SKILL.md) and [`agenc-review`](../agenc-review/SKILL.md) for this role.

5. BLUE TEAM: Launch only AgenC runs (not chat bots). The members for a project are chosen by the separate skill [`blue-team-roster`](../blue-team-roster/SKILL.md) (script blue-team-roster/pick_roster.py: JSON in, roster + skipped + launch order out). Run `python3 blue-team-roster/pick_roster.py <project.json>` (JSON in: modules_touched, new_modules, cross_boundary_count, money_or_state, parallel_units, mechanical_edit_count, diff_lines, interface_changes, perf_claims, project_size, confirmed_findings, three_strike) and launch only the members in its roster in its launch order. Save its output in <job-dir>/packets/. Not every member is on every project; use the smallest roster that covers the risks.

Core 4 members the gates always reference:

| Role | Job | Brief template line | Inputs | Outputs | Done-check |
|------|-----|---------------------|--------|---------|------------|
| Builder (core) | Implements one unit from the spec plus its tests; updates engineering docs for what it touched (architecture, module notes, decisions, gaps) | You are the Builder. Implement unit <id> from <spec> with its tests inside <file scope>, update the engineering docs you touched, and write the diff summary and test list to <out>/build-<id>.md. | SPEC.md, unit brief, scope | diff, test list, doc updates | Verifier run passes; diff inside file scope; docs updated |
| Verifier (core) | Separate AgenC run that does not trust the builder. Runs the full suite and drives the real thing (CLI or API) like a user; saves literal output as the artifact. Does not edit code | You are the Verifier. Do not trust the Builder. Run <suite cmd>, drive <CLI/API> like a user, save literal output to <out>/verify-<id>.txt and edit no source files. | BUILD.md, code at sha | literal output artifact, suite results | output captured, no edits made; `git status --porcelain` empty after the run (you read it) |
| Fixer (event: confirmed finding) | Takes only confirmed findings (a repro or cross-check confirmation). Writes a failing test first, makes the smallest fix, reruns the full suite | You are the Fixer. For confirmed finding <finding id>, write failing test first, make smallest fix, rerun full suite, and write fixed code and new test to <out>/fix-<id>.md. | confirmed finding + repro | failing test + minimal fix diff, new suite run | test passes, diff minimal |
| Rebuilder (event: three-strike write-up) | Runs only on a three-strike write-up (see [`three-strike-rebuild`](../three-strike-rebuild/SKILL.md)). Re-derives from the spec and data shape from a new perspective; must not reuse the failed premise | You are the Rebuilder. From the write-up <writeup path>, spec and data shape, rebuild without the failed premise, and write new implementation to <out>/rebuild-<id>.md. | write-up, spec, data shape | new diff + tests from clean base | fresh derivation, test passes |

Optional members (Architect, Test Author, Integrator, Codemod Smith, Simplifier, Blast-Radius Reviewer, Bench Runner, Docs Writer) are defined in [`blue-team-roster`](../blue-team-roster/SKILL.md).

RED TEAM (audits) is a separate independent team. Blue and red never share a run and never grade each other's own work.

6. Gates, in order: (roster pre-build members such as Architect/Test Author/Integrator per [`blue-team-roster`](../blue-team-roster/SKILL.md)) Builder -> Verifier -> red team audit on the same sha -> independent cross-check of findings (see [`xmodel-confirm`](../xmodel-confirm/SKILL.md)) -> Fixer on confirmed findings (re-verify and re-audit the new sha) -> three strikes on the same failure lead to the write-up and blue-team Rebuilder (see [`three-strike-rebuild`](../three-strike-rebuild/SKILL.md); Fixer on hold) -> CLEAR packet -> human approval before anything ships. Map to <job-dir>/packets/ files: SPEC.md (intake), BUILD.md (builder), AUDIT.md (red team), CLEAR.md (final).

After three strikes the Fixer stops for that failure (pick_roster.py marks it "on hold") and only the Rebuilder runs.

7. Cost: Snapshot the key usage before and after (see [`agenc-spend-guard`](../agenc-spend-guard/SKILL.md) for snapshot/check), print only limit, limit_remaining, usage. Never any CLI's own cost estimate. Several children share one key, so per-unit numbers are "polluted"; your own lead run uses the same key, so the job delta includes the lead; report the job total as the settled delta and label per-unit numbers polluted.

8. Report: Short status (what finished, what's blocked, real cost, next step) plus a handoff packet (see [`agenc-handoff`](../agenc-handoff/SKILL.md)). Write the report + handoff packet to the designated handoff location; if the sandbox denies the write, write under the job dir and name the path. Your final message is the 4-line status plus the packet path. A human approver is asked for the OK; you never ship.

If the OS sandbox denies a write to <job-dir>/packets/ or the handoff location, write the same files under <job-dir>/handoff/ and name that path in your final message; do not try to escalate permissions.

Use 4-line status template:

```
Finished: <job-id>: <units>
Blocked: <issues or none>
Cost: $<settled delta> real (key delta; includes this lead run; polluted: yes/no)
Next: <step or escalate>
```

9. Never: push, deploy, merge to main, restart the daemon, or relaunch a job a human stopped; never write or test code yourself; never print keys; no secrets in briefs. See [`agenc-retry`](../agenc-retry/SKILL.md) for attempt limits but you control all relaunches.
