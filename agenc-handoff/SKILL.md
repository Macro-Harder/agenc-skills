---
name: agenc-handoff
description: Use when work moves between agents, from a lead to AgenC subagents and back, between sequential AgenC runs, or from an agent to a human, and the next owner must pick it up from a file instead of a chat summary.
---
# Hand off work through packets

Context moves in files, not chat. Chat may point at the packet. It is never the payload.

A packet is one Markdown file with fixed fields. The receiver reads it first and trusts it over any summary. Checked against AgenC 0.19.9.

## 1. When to write a packet

| Handoff | Sender | Receiver | Packet goes |
|---|---|---|---|
| Agent to agent | the agent stopping | the agent continuing | path in the message that hands over |
| Lead to subagent | lead | AgenC subagent | path in the subagent's brief |
| Subagent to lead | subagent | lead | path in the subagent's final message |
| Run to next run | run N | run N+1 | path in run N+1's brief |
| Agent to human | agent | the person who decides | path in the one note to them |

Write one whenever work stops before it is done, changes owner, or crosses a run boundary. A run that finishes and is verified on the spot needs none.

## 2. Where packets live

One handoff root per job, outside any repo worktree:

| Folder | Holds |
|---|---|
| `New/` | Packets being written |
| `Incomplete/` | STATUS `partial` or `blocked` |
| `Complete/` | STATUS `complete` |

Move the file when STATUS changes. Supporting files sit beside the packet.

Name: `{sender}-to-{receiver}-HANDOFF-{n}.md`. `n` is the next free number for that pair across all three folders. Never write a bare `HANDOFF.md`; the next handoff overwrites it. Use short, stable names such as `lead`, `sub-parser`, `run-2`, `reviewer`, `human`.

## 3. Required fields

Every field has a value. Write `none` or `not run, because ...` rather than leaving one empty.

| Field | Contents |
|---|---|
| `TASK` | What you were asked to do. |
| `STATUS` | Exactly one of `complete`, `partial`, `blocked`. |
| `OUTPUT` | Paths to the deliverables. |
| `BASE` | For code: repo, base sha the work started from, head sha, branch, worktree path. Otherwise `none`. |
| `VERIFY` | The exact command you ran and its literal result, pasted. |
| `COST` | Real spend from the provider usage endpoint, and whether usage had settled. |
| `SOURCES` | Files, links, logs, timestamps you worked from. |
| `DECISIONS` | Judgment calls and why. |
| `UNCERTAINTIES` | What you could not verify. |
| `NEXT OWNER` | Who continues, and their first step. |
| `DO NOT ASSUME` | Facts the receiver must re-check. |

- **STATUS has three values.** There is no "mostly done". Unverified work is `partial`.
- **VERIFY is evidence, not a claim.** "Tests pass" is not a VERIFY. `pytest tests/test_x.py` followed by `12 passed in 0.31s` is.
- **COST comes from the provider.** Never AgenC's `costUsd` estimate. See [`agenc-spend-guard`](../agenc-spend-guard/SKILL.md).
- **BASE is a sha, not a branch name.** Branches move. The receiver diffs against the sha.
- **No secrets.** No keys, tokens, passwords, or private data. Name the env var that holds a credential, never its value. Packets get copied into briefs and logs.

## 4. The helper

`handoff.py` (in this folder, Python 3.8+ standard library only):

```bash
p=$(python3 handoff.py new --root "$JOB/handoffs" --from lead --to sub-parser)
# fill every field in "$p"
python3 handoff.py check "$p"                    # exit 1 lists missing or empty fields
python3 handoff.py move "$p" --status partial    # sets STATUS, moves to Incomplete/
python3 handoff.py move "$p" --status complete   # refused unless check passes
```

- `new` creates the three folders if needed, picks the next free `n`, writes the template, prints the path.
- `check` also rejects a STATUS outside the three values and lines that look like secrets.
- `move --status complete` leaves the packet untouched if any field is missing.
- Exit codes: `0` ok, `1` incomplete or refused, `2` usage error.

## 5. Sending

1. Fill every field. Paste VERIFY output; do not retype it.
2. For code, record the base sha you started from, `git -C <worktree> rev-parse HEAD`, and `git -C <worktree> status --short`. Put all three in `BASE`.
3. Run `check`. Fix until it exits 0. Validate at the boundary, before the packet leaves, not after the receiver trips on a gap.
4. `move` to the folder that matches STATUS.
5. Hand over the path. Nothing else goes in the message but one line of what it is.

## 6. Packets in AgenC briefs

The next run sees only its brief and its directory. Put the packet path in the brief's Context section and copy the packet into the run's directory if the run cannot read outside it:

```text
Context: Read handoffs/Incomplete/run-1-to-run-2-HANDOFF-1.md first. It is the source of truth.
Re-check every item under DO NOT ASSUME before relying on it.
Start from base <sha> in <worktree>.
Before your final message, write handoffs/New/run-2-to-lead-HANDOFF-<n>.md with every field filled.
```

Follow [`agenc-briefs`](../agenc-briefs/SKILL.md) for the rest of the brief. In plan or `acceptEdits` mode the run cannot run the helper; tell it to write the packet as a file and run `check` yourself afterward.

## 7. Receiving

1. Read the packet before any chat summary. Where they disagree, the packet wins; where the packet is wrong, the files win.
2. Run `check`. An incomplete packet goes back to the sender, or the gaps go under your own UNCERTAINTIES.
3. Re-run the VERIFY command yourself. A pasted result is the sender's evidence, not yours.
4. Confirm BASE: `git -C <worktree> rev-parse HEAD` matches the head sha, and `git -C <worktree> diff <base sha>` shows only what OUTPUT claims.
5. Work through DO NOT ASSUME before building on anything.

## 8. By role

- **Lead and subagents.** Each subagent gets its own pair name and returns one packet. The lead runs `check` on every returned packet before reviewing the code. See [`agent-with-subagents`](../agent-with-subagents/SKILL.md) and [`agenc-review`](../agenc-review/SKILL.md).
- **Blocked subagent.** STATUS `blocked`, the question under UNCERTAINTIES, the escalation under NEXT OWNER. It follows [`agenc-escalate-to-lead`](../agenc-escalate-to-lead/SKILL.md); the packet carries the state, the escalation carries the question.
- **Sequential runs.** Run N's packet is run N+1's only memory. Never rely on chat history or a resumed session to carry decisions.
- **Agent to human.** Receiver `human`. Put the decision needed in the first line of NEXT OWNER. Give options and a recommendation. The human should not need to open anything else to decide.
