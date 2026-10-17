---
name: blue-team-roster
description: Use when a lead (AgenC lead run) must decide which blue-team members to launch on a project, from risk signals, before dispatch.
---

# blue-team-roster

Decides which blue-team members (AgenC agent roles, launched as AgenC runs by the lead) are used on a project. Not every member is on every project. Principle: the smallest roster that covers the risks; justify every member added. Used by the [`agenc-lead`](../agenc-lead/SKILL.md) before dispatch. Red team (audits) is separate and not in this roster.

## When to use
At intake, after the units are cut. Re-run when findings are confirmed or a three-strike write-up appears.

## How
Write `project.json`. Run:
```
python3 pick_roster.py project.json
```
(or `blue-team-roster/pick_roster.py`); save output as `<job-dir>/packets/ROSTER.json`. Bad input yields `{"error": ...}` and exits 2.

## Input fields
| Field | Default |
|-------|---------|
| modules_touched | 1 |
| new_modules | 0 |
| cross_boundary_count | 0 |
| money_or_state | false |
| new_core_types | false |
| builder_tests_only_proof | false |
| parallel_units | 1 |
| mechanical_edit_count | 0 |
| diff_lines | 0 |
| refactor_or_migration | false |
| interface_changes | false |
| perf_claims | false |
| project_size | small |
| new_subsystem | false |
| confirmed_findings | 0 |
| three_strike | false |

## Members
| Member | Kind | Trigger | Job |
|--------|------|---------|-----|
| Builder | core | always | implement one unit from the spec plus its tests; update the engineering docs for what it touched |
| Verifier | core | always | independent check: run the full suite and drive the real thing (CLI or API) like a user; never edits code |
| Architect | optional | new_modules > 0 or cross_boundary_count > 1 or new_core_types | name data shapes, types and module boundaries before any build |
| Test Author | optional | money_or_state or builder_tests_only_proof | write behaviour tests from the spec independently of the Builder |
| Integrator | optional | parallel_units >= 2 | merge parallel worktrees in order, resolve conflicts, hand off to the Verifier |
| Codemod Smith | optional | mechanical_edit_count >= 5 | write a script or codemod for bulk mechanical changes instead of hand edits |
| Simplifier | optional | diff_lines > 400 or refactor_or_migration | delete dead code, shims, one-caller wrappers and comment slop |
| Blast-Radius Reviewer | optional | interface_changes | find callers and dependents a change could break; read-only |
| Bench Runner | optional | perf_claims | measure any perf claim and name the limiter |
| Docs Writer | optional | project_size == "large" or new_subsystem | standalone docs for a large project or new subsystem |
| Fixer | event | confirmed_findings > 0 (on hold if three_strike) | fix confirmed findings only: failing test first, smallest fix, full suite rerun |
| Rebuilder | event | three_strike | rebuild from the spec and data shape after a three-strike write-up; never reuse the failed premise |

## Per-member details
| Member | inputs | outputs | done_check | brief_line |
|--------|--------|---------|------------|------------|
| Builder | spec, unit boundary from Architect, existing code in scope | diff, test list, doc updates | unit tests pass in the Verifier run; diff inside file scope | You are the Builder. Implement unit <id> from <spec> with its tests inside <file scope>, update the engineering docs you touched, and write the diff summary and test list to <out>/build-<id>.md. |
| Verifier | the integrated code, test suite, real usage scenarios | literal output artifact | suite and real-use outputs saved verbatim; verdict PASS/FAIL per done-check | You are the Verifier. Do not trust the Builder. Run <suite cmd>, drive <CLI/API> like a user, save literal output to <out>/verify-<id>.txt and edit no source files. |
| Architect | project scope, modules_touched, cross_boundary_count, new_core_types, new_modules | design note with types and boundaries | every unit maps to a named boundary; no build starts before it | You are the Architect. Name data shapes, types and module boundaries from <project scope>, <modules_touched>, <cross_boundary_count>, <new_core_types> and <new_modules> before any build, and write the design note to <out>/design-<id>.md. |
| Test Author | spec, money_or_state, builder_tests_only_proof | test files that fail before the build | tests fail on the base sha and cite spec lines | You are the Test Author. Write behaviour tests from <spec> independently of the Builder using <money_or_state> and <builder_tests_only_proof>, and write the test files to <out>/test-<id>.md. |
| Integrator | parallel_units, parallel branches from Builders | one integrated branch and merge log | all unit branches merged; no conflict markers; handed to Verifier | You are the Integrator. Merge parallel worktrees in order from <parallel_units> and <parallel_branches_from_builders>, resolve conflicts, hand off to the Verifier, and write one integrated branch and merge log to <out>/integrate-<id>.md. |
| Codemod Smith | mechanical_edit_count, files or call sites | codemod script plus its diff | rerunning the codemod on the result is a no-op | You are the Codemod Smith. Write a script or codemod for <mechanical_edit_count> and <files_or_call_sites> instead of hand edits, and write the codemod script plus its diff to <out>/codemod-<id>.md. |
| Simplifier | diff_lines, refactor_or_migration | a diff that reduces line count | net lines removed; suite unchanged | You are the Simplifier. Delete dead code, shims, one-caller wrappers and comment slop from <diff_lines> and <refactor_or_migration>, and write a diff that reduces line count to <out>/simplify-<id>.md. |
| Blast-Radius Reviewer | interface_changes | list of affected callers with file:line | every changed interface has its callers listed and checked | You are the Blast-Radius Reviewer. Find callers and dependents a change could break from <interface_changes>, list of affected callers with file:line to <out>/blast-<id>.md and edit no source files. |
| Bench Runner | perf_claims | benchmark command, raw numbers, limiter | each number has a command, raw output and named limiter | You are the Bench Runner. Measure any <perf_claims> and name the limiter, write benchmark command, raw numbers, limiter to <out>/bench-<id>.md and edit no source files. |
| Docs Writer | project_size, new_subsystem | docs files | docs match the code at the sha | You are the Docs Writer. Write standalone docs for <project_size> and <new_subsystem>, and write docs files to <out>/docs-<id>.md. |
| Fixer | confirmed_findings | fixed code, new test | new test fails before, passes after; full suite green in a Verifier run | You are the Fixer. For confirmed finding <finding id>, write failing test first, make smallest fix, rerun full suite, and write fixed code and new test to <out>/fix-<id>.md. |
| Rebuilder | three_strike | new implementation from spec | write-up's shared premise named and not relied on; Verifier passes | You are the Rebuilder. From the write-up <writeup path>, spec and data shape, rebuild without the failed premise, and write new implementation to <out>/rebuild-<id>.md. |

## Launch order (stages)
Architect -> Test Author in parallel with Builders -> Codemod Smith -> Integrator -> Simplifier -> Blast-Radius Reviewer -> Verifier -> Bench Runner -> Docs Writer. Fixer and Rebuilder are event-driven. Red team audits the sha after the Verifier, per [`agenc-lead`](../agenc-lead/SKILL.md) gates.

## Output fields
- roster: [{member, kind, reason}, ...]
- skipped: [{member, reason}, ...]
- launch_order: [[active stages], ...]
- event_driven: [{member, status, trigger}, ...]
- inputs: resolved values
- size: roster length
- principle: "smallest roster that covers the risks; every member justified"

## Rules
- Every launched member must be in roster with its reason.
- Do not add a member the script skipped without writing the reason in SPEC.md DECISIONS.
- Never drop a core member.
- Blue members never grade red work and vice versa.

## Fixture examples
| Fixture | Roster | Launch order | Event driven |
|---------|--------|--------------|--------------|
| bulk-rename-20-files.json | Builder, Codemod Smith, Simplifier, Blast-Radius Reviewer, Verifier | [['Builder'], ['Codemod Smith'], ['Simplifier'], ['Blast-Radius Reviewer'], ['Verifier']] | Fixer (on trigger), Rebuilder (on trigger) |
| cross-module-money.json | Architect, Test Author, Builder, Integrator, Simplifier, Blast-Radius Reviewer, Verifier | [['Architect'], ['Test Author', 'Builder'], ['Integrator'], ['Simplifier'], ['Blast-Radius Reviewer'], ['Verifier']] | Fixer (on trigger), Rebuilder (on trigger) |
| perf-claim.json | Builder, Verifier, Bench Runner | [['Builder'], ['Verifier'], ['Bench Runner']] | Fixer (on trigger), Rebuilder (on trigger) |
| three-strike.json | Test Author, Builder, Verifier, Rebuilder | [['Test Author', 'Builder'], ['Verifier']] | Fixer (on hold), Rebuilder (launch now) |
| tiny-bugfix.json | Builder, Verifier | [['Builder'], ['Verifier']] | Fixer (on trigger), Rebuilder (on trigger) |
