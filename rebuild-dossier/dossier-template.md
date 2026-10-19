# REBUILD-DOSSIER-<unit>

<!-- Append-only. Add new entries with a round tag (R2, R3...). Never delete or rewrite
earlier content; strike wrong facts with ~~ and add a dated correction. -->

## Header
- Unit: <unit>
- Branch / base sha: <branch> @ <sha>
- Round: <N>
- Date and time: <YYYY-MM-DD HH:MM TZ>
- Author: <builder or lead agent>
- Job docs: <folder with SPEC.md and DECISIONS.md>

## Goal and acceptance bar
<what done means, from SPEC.md>

## Known knowns
- (R1) <fact> - evidence: <test id | command | file path>
  ```
  <literal output, trimmed to the relevant lines>
  ```

## Known unknowns
- (R1) <question> - how to find out: <method> - cost: <rough cost or time>

## Unknown-unknown risks
- (R1) <area: concurrency | restart/resume | external API | data shape | clock/timezone | partial writes | rate limits> - <why a surprise is likely here>

## Failed premises
- (R1) Premise: <what the attempt believed> - why it failed: <reason> - evidence: <ref>. DO NOT REUSE.

## What to keep
- (R1) <test / fixture / type / repro> - path: <path> - why: <reason>

## What to throw away
- (R1) <code or approach> - why: <reason>

## Constraints and hard limits
- (R1) <scope, files not to touch, budget, deadline, safety rule>

## Verification bar
- (R1) `<exact command>` -> expected: <result>; artifact: <path>

## Cost and attempts so far
| Round | Attempts | Real spend (key delta) | Notes |
|-------|----------|------------------------|-------|
| R1 | <n> | $<x> | <polluted yes/no> |
| Total | <n> | $<x> | |

## Recommended first step for the rebuilder
- (R1) <one concrete first action>

# Round history (newest first)

<!-- New rounds go directly below this line as `## Round N`. -->

## Round 1
- Date and time: <YYYY-MM-DD HH:MM TZ>; author: <who>
- Trigger: <three-strike-rebuild | red-team FINDINGS | lead agent restart>
- What was built and how it failed: <summary + evidence>
- New failed premise: <premise>
- Source write-up: <path to WRITEUP-<id>.md, if three-strike-rebuild>
- Handed to lead agent: <YYYY-MM-DD HH:MM TZ>, sha256 <hash> (from DECISIONS.md)
