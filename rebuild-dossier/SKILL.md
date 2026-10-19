---
name: rebuild-dossier
description: >-
  Use when a build or fix has failed and a unit is being sent to a from-scratch
  rebuild (three-strike-rebuild, a red-team FINDINGS verdict that sends it back
  to scratch, or the lead agent restarting it). Write or extend an append-only
  REBUILD-DOSSIER-<unit>.md (known knowns, known unknowns, failed premises, what
  to keep, verification bar) and hand it to the lead agent before the new build starts.
---

# rebuild-dossier

A from-scratch rebuild throws away code, not knowledge. The dossier carries what the
failed rounds proved, what they could not settle, and which premises must not come back.
No dossier, no rebuild.

## When to use
- [`three-strike-rebuild`](../three-strike-rebuild/SKILL.md) fired (3 failed fixes on the same test or bug), or
- a red-team FINDINGS verdict sends a unit back to scratch, or
- the lead agent decides to restart a unit from a clean base.

Not for an ordinary fix on the same branch; that stays with the Fixer.

## Who writes it, where
The failing builder writes it; if the builder is gone or wedged, the lead agent writes it.
File: `REBUILD-DOSSIER-<unit>.md` in the job docs folder (same folder as SPEC.md and
DECISIONS.md). Start from `dossier-template.md` beside this SKILL.md. If the file already
exists, extend it (see Append-only); never start a second dossier for the same unit.

## Sections (all required; write "none" rather than dropping one)
1. Header: unit, branch or base sha, round number, date and time (with time zone), author.
2. Goal and acceptance bar: what done means, from SPEC.md, in one paragraph.
3. Known knowns: facts proven, each with its evidence (test id, exact command, literal
   output trimmed to the relevant lines, or file path). A claim without evidence goes
   under Known unknowns.
4. Known unknowns: each open question, how to find out, and roughly what it costs to find out.
5. Unknown-unknown risks: where surprises are likely (concurrency, restart/resume, external
   API behaviour, data shape drift, clock/timezone, partial writes, rate limits).
6. Failed premises: every premise tried, why it failed, the evidence, and "DO NOT REUSE".
7. What to keep (tests, fixtures, types, repros worth carrying over, with paths) and what
   to throw away (with the reason).
8. Constraints and hard limits: scope, files not to touch, budget, deadlines, safety rules.
9. Verification bar: the exact commands and artifacts that prove done.
10. Cost and attempts so far: real spend (key usage delta, never the CLI cost estimate; see [`agenc-spend-guard`](../agenc-spend-guard/SKILL.md)) and
    attempt count, per round and total.
11. Recommended first step for the rebuilder.
12. Round history, newest first.

## Append-only
- On a second or later fresh rebuild, add a new `## Round N` section at the top of the
  Round history: what changed, the new facts (with evidence), the new failed premise, and
  the spend for that round. Bump the round number in the Header.
- New entries in the living sections (3-11) are added with a round tag, e.g. `(R2)`.
- Move an item between Known unknowns and Known knowns only by adding a dated note
  (`<YYYY-MM-DD HH:MM TZ> R2: proven, see <evidence>`); keep the original line.
- A fact that turned out wrong: `~~old fact~~` plus a dated correction on the next line.
- Never delete or rewrite earlier rounds, failed premises, or evidence.

## Handoff gate (before the new build starts)
1. The author hands the dossier path to the lead agent running the job (see [`agenc-lead`](../agenc-lead/SKILL.md)).
2. The lead agent records receipt in DECISIONS.md, one line:
   `<YYYY-MM-DD HH:MM TZ> rebuild-dossier received: unit=<unit> round=<N> sha256=<sha256sum of the file> path=<path>`
   Any edit after receipt changes the hash and needs a new receipt line.
3. The lead agent puts the dossier in the rebuilder's brief: verbatim, or its path plus "read it
   first, before any code".
4. The rebuilder's first output is a short statement, one line per failed premise, of how
   its approach avoids it. The lead agent checks it against the list; if any premise is reused or
   skipped, the build does not start.
No dossier, no receipt, or no premise statement: no rebuild.

## Repeat rebuilds and escalation
If the rebuild fails and goes back to scratch again, the dossier gets a new round (Append-only)
and goes back to the lead agent through the same gate. The lead agent escalates to a human only when the rounds
are not converging: the same failed premise shows up twice, no new known knowns in a round,
or the budget is hit. The escalation carries the dossier path and its latest sha256.

## Relation to three-strike-rebuild
The [`three-strike-rebuild`](../three-strike-rebuild/SKILL.md) WRITEUP-<id>.md becomes Round 1 of the dossier: paste its facts into the
sections and link or attach the write-up file under Round 1.

## Checklist
- [ ] Dossier created from the template, or extended with a new `## Round N` at the top
- [ ] Every known known has evidence; every failed premise says DO NOT REUSE
- [ ] Nothing earlier deleted; corrections struck through and dated
- [ ] Handed to the lead agent; receipt (round, sha256) in DECISIONS.md
- [ ] Dossier verbatim or path + "read first" in the rebuilder's brief
- [ ] Rebuilder's premise-avoidance statement checked before the build starts
