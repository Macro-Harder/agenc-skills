---
name: agenc-escalate-to-lead
description: Use when a lead agent dispatches AgenC subagents and needs them to stop and escalate to the lead (not guess, not ask a human) when blocked or out of attempts, and when the lead must triage and settle those escalations.
---
# Escalate from subagent to lead

A blocked subagent stops and asks its lead. The lead settles what it can. Only what the lead cannot settle goes to a human, once, in one note.

This extends [`agent-with-subagents`](../agent-with-subagents/SKILL.md) (lead and subagent roles) and [`agenc-retry`](../agenc-retry/SKILL.md) (3 attempts per unit). Checked against AgenC 0.19.9.

## 1. When a subagent escalates

The subagent stops and escalates when:
- Two requirements in its brief conflict.
- The fix needs a file, tool, or decision outside its scope fence.
- It lacks access: a credential, a service, a file that is not there.
- It has failed its done condition 3 times.

It never guesses on a decision outside its fence. It never widens its own scope. It leaves partial work in place and says so.

## 2. The escalation contract

Paste this into every subagent brief, after the output contract:

```text
Escalation contract:
If the requirements conflict, a needed decision is outside the files you may edit, or you are blocked, do not guess and do not edit anything. Stop and make your final message exactly the line ESCALATION followed by one JSON object with these fields:
{"unit": "<unit id>", "goal": "<goal>", "blocker": "conflict|missing_access|out_of_scope|repeated_failure|other",
 "attempts": [{"summary": "<what you tried>", "exit": null, "error": "<key error or finding>"}],
 "ruled_out": ["<option you checked and why it fails>"], "question": "<the one decision you need>",
 "options": ["<option A: tradeoff>", "<option B: tradeoff>"], "recommendation": "<which option and why>",
 "partial": <true if you changed any file, else false>}
Otherwise your final message is exactly one line: `RESULT: PASS <summary>` or `RESULT: FAIL <reason>`.
```

- The final message is the channel. It lands in the result file, outside the diff.
- `question` is one decision, answerable in a sentence. "What should I do?" is not a question.
- `options` and `recommendation` let the lead answer by picking, not by redoing the analysis.
- If your harness lets the subagent write outside its tree, an `ESCALATION.json` with the same fields works too. Never inside the diff.

## 3. Detect escalations

Use one result file per unit, as in [`agent-with-subagents`](../agent-with-subagents/SKILL.md): `<out>/<unit>.json`, `<unit>.err`, `<unit>.exit`. `triage_escalations.py` (in this folder, Python standard library only) scans them:

```bash
python3 triage_escalations.py /tmp/job/out --worktrees /tmp/job
```

```text
unit       exit  status     redisp  next          question
slug-case  0     ESCALATED  0/2     lead decides  Which takes precedence: the goal (preserve case, so tests/test_slug.py
```

Then one block per escalation: blocker, partial, options, recommendation, ruled-out items.

- Exit `0`: nothing to triage. Still verify every `DONE?` unit yourself.
- Exit `1`: escalations, failures, or missing results.
- `ESCALATED(bad)` means the subagent broke the contract (bad JSON or missing fields). Treat it as a failed attempt under [`agenc-retry`](../agenc-retry/SKILL.md).
- An escalation can arrive with exit `0`. Never treat exit `0` alone as done.

## 4. The lead decides

For each escalation, in this order:

1. **Answer it.** If the decision is inside the lead's authority (the goal, the scope, the brief), decide. Add the answer to the brief as a fact, not a hint: "Decision: keep lowercase; the goal line was wrong." Re-dispatch from a fresh worktree.
2. **Check it yourself.** If the question is a fact the lead can look up or test (does this file exist, does this command pass), find out and answer. Do not forward checkable questions.
3. **Change the approach.** If the unit hit the same wall twice, the premise is wrong. Redesign the unit, split it, or merge it with the unit it conflicts with.
4. **Do it yourself.** If the answer is short and you already know it.
5. **Escalate to a human.** Only for what the lead cannot settle within its authority:
   - irreversible actions (push, deploy, delete, send, spend beyond the budget)
   - missing credentials or access
   - product or policy decisions
   - requirements that conflict at the goal level, not in one brief

The lead never forwards a raw subagent escalation to a human. It checks it, answers what it can, and sends one consolidated note.

## 5. Budget: no loops

- Each unit has a stable id. Its worktree, result files, and counters are named after it. Re-running the lead does not duplicate work.
- **At most 2 lead-answered re-dispatches per unit.** Count them in `<out>/<unit>.redispatch`. The triage table shows `redisp n/2`.
- Failed attempts count separately under [`agenc-retry`](../agenc-retry/SKILL.md): 3 per unit.
- When either limit is reached, the lead does the unit itself or escalates to a human. No third answer, no fourth attempt.

```bash
u=slug-case; n=$(( $(cat "$OUT/$u.redispatch" 2>/dev/null || echo 0) + 1 ))
[ "$n" -le 2 ] || { echo "$u: re-dispatch limit reached; do it yourself or escalate"; exit 1; }
echo "$n" > "$OUT/$u.redispatch"
cat "$JOB/briefs/$u.md" > "$JOB/briefs/$u.r$n.md"
printf '\nDecision from lead (re-dispatch %s): %s\n' "$n" "$ANSWER" >> "$JOB/briefs/$u.r$n.md"
# fresh worktree, then dispatch with briefs/$u.r$n.md as in agent-with-subagents
```

## 6. Human escalation note

One note for the whole job, covering every unit the lead could not settle:

```text
ESCALATION: <job>
Goal: <job goal>
Done without you: <units finished and verified>
Needs you:
- <unit>: <question, one sentence>
  Options: <A> / <B>. Lead recommends <A> because <reason>.
  Tried: <attempts and re-dispatches, exit codes, key errors>
  Ruled out: <what the lead checked>
  Evidence: <result files, logs, diffs>
Blocked until answered: <units>. Everything else continues.
```

Keep working on units that do not depend on the answer. Do not block the whole job on one question.

## 7. Verify escalations too

An escalation is a claim like any other. Before acting on it:
- Confirm the conflict is real: read the brief and the files it names.
- Confirm `partial`: `git -C <worktree> status --short`. An escalation that says `false` but left changes broke the contract.
- If the subagent was wrong (no real conflict), sharpen the brief and count it as a failed attempt under [`agenc-retry`](../agenc-retry/SKILL.md).
