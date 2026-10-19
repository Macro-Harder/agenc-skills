---
name: three-strike-rebuild
description: Use when a fix for the same failing test or bug has failed three times; stop retrying, write a structured write-up, and hand it to the blue team to rebuild the fix from a new perspective as an AgenC job.
---

## When to use
The same failing test (or the same bug) has had 3 fix attempts that did not make it pass, or "passed" only by weakening the test. Count attempts per test/bug, not per session. Do not start a 4th attempt.

## Step 1 - Stop
No further patches on the current approach. Keep the branches/diffs of all three attempts.

## Step 2 - Write the write-up using writeup-template.md
writeup-template.md is placed beside this SKILL.md. The filled document is saved next to the work as `WRITEUP-<test-or-bug-id>.md`.

Required content:
- the bug (expected vs actual)
- the repro or failing test id and exact command
- for EACH of the 3 attempts: the premise (what the attempt believed the cause was), a diff summary (files and the gist of the change), why it failed, and the literal test output (pasted verbatim, not paraphrased, trimmed only to the relevant failure)
- the shared premise the three attempts had in common
- what was NOT tried
- open questions

Keep it short: facts over narrative.

This write-up becomes Round 1 of the unit's rebuild dossier (see [`rebuild-dossier`](../rebuild-dossier/SKILL.md)): create `REBUILD-DOSSIER-<unit>.md` from its template and fill it from the write-up, or attach the write-up under Round 1.

## Step 3 - Hand off to the blue team
Send the write-up (and links to the attempt diffs) to the blue team through the normal hand-off channel. The individual working on the fix does not continue on it.
The hand-off goes through the rebuild-dossier gate: the dossier is handed to the lead agent before the rebuild starts, the lead records receipt (round number and sha256 of the dossier) in DECISIONS.md, and the rebuilder's brief includes the dossier verbatim or its path with "read it first". No dossier, no rebuild.

## Step 4 - Blue team rebuild (runs as an AgenC job)
The rebuilder's first output is one line per failed premise in the dossier saying how its approach avoids it.
Before writing code, re-read the spec/requirements and the actual data shape (inputs, outputs, stored state, real example records) and write down a fresh statement of the cause. Explicitly list the shared premise from the write-up and state why the new approach does not rely on it. Reusing the failed premise is not allowed. Prefer starting from the clean base, not from any attempt branch. Write or keep the failing test first, then the fix. The job prompt includes the write-up, the spec section, and the rule "do not reuse the failed premise".

## Step 5 - Normal review and audit
The rebuild goes through the usual code review and audit like any other change, and the write-up is linked in the change description. The dossier is linked too. If the rebuild also fails and goes back to scratch, the dossier gets a new `## Round N` at the top of its history (append-only, nothing deleted) and goes back to the lead agent through the same gate (see [`rebuild-dossier`](../rebuild-dossier/SKILL.md)). Escalate to a human owner only if the lead judges the rounds are not converging (for example the same failed premise twice, or the budget hit), with the dossier path.

## Checklist
- [ ] Three attempts documented with premises, diffs, failures, and outputs
- [ ] Write-up created from the template
- [ ] Write-up is Round 1 of REBUILD-DOSSIER-<unit>.md (or attached to it)
- [ ] Dossier handed to the lead before the rebuild; receipt (round, sha256) in DECISIONS.md
- [ ] Write-up sent to blue team
- [ ] Rebuild performed as AgenC job from clean base
- [ ] Rebuild reviewed and audited
- [ ] Write-up referenced in the change description
