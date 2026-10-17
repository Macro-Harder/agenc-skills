# AgenC agent skills

Agent skills for driving the [AgenC](https://get.agenc.ag) coding-agent CLI from another agent: offloading work, writing briefs, reviewing results, retrying, escalating, handing off, capping spend, and running unattended.

| Skill | Use when |
|---|---|
| [agenc-cli](agenc-cli/SKILL.md) | You need the AgenC CLI basics: headless invocation, flags, permissions, output, daemon, troubleshooting. |
| [agenc-offload](agenc-offload/SKILL.md) | You want to hand heavy, self-contained work to a headless AgenC run and verify the result yourself. |
| [agent-with-subagents](agent-with-subagents/SKILL.md) | A lead agent splits a job, dispatches subagents, then verifies and merges their results. |
| [agenc-briefs](agenc-briefs/SKILL.md) | You are writing the brief for an AgenC run and want it right the first time. |
| [agenc-review](agenc-review/SKILL.md) | An AgenC run produced a change and you must accept, fix, or reject it. |
| [agenc-retry](agenc-retry/SKILL.md) | A run failed, hit a cap, or returned bad work, and you must decide what to do next. |
| [three-strike-rebuild](three-strike-rebuild/SKILL.md) | Three fix attempts on the same failing test or bug have failed, so stop retrying, write a structured summary, and hand it to the blue team as an AgenC job to rebuild from a new perspective. |
| [agenc-escalate-to-lead](agenc-escalate-to-lead/SKILL.md) | Subagents must stop and escalate to their lead instead of guessing, and the lead must triage them. |
| [agenc-handoff](agenc-handoff/SKILL.md) | Work moves between agents, runs, or to a human, and the next owner must pick it up from a file, not chat. |
| [agenc-spend-guard](agenc-spend-guard/SKILL.md) | A job must stay under a dollar limit, measured from your provider's real usage. |
| [agenc-batching](agenc-batching/SKILL.md) | Many small independent asks would each pay the fixed per-run prompt overhead; batch them into one run. |
| [agenc-unattended](agenc-unattended/SKILL.md) | You run AgenC from cron, CI, or other automation nobody is watching. |
| [xmodel-confirm](xmodel-confirm/SKILL.md) | An auditor or red team reports bugs and you want to know if a different model independently finds or confirms each one before acting on it. |
| [agenc-lead](agenc-lead/SKILL.md) | A team of AgenC subagent runs for intake, roster, dispatch, watch, independent verification, red team gates, real cost, report and handoff needs oversight; a lead agent manages them. |
| [blue-team-roster](blue-team-roster/SKILL.md) | Risk signals from a project call for deciding blue-team member roles to launch; select the smallest roster that covers the risks. |

Install: copy the skill folders you want into your agent's skills directory. Each folder is a `SKILL.md` plus any helper script it uses. Skills link to each other by relative path, so copy the ones they reference too.

Requires AgenC, installed from https://get.agenc.ag. Helper scripts need only bash or the Python 3.8+ standard library.
