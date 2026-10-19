---
name: agenc-run-status
description: Use when you need the real status of a supervised AgenC lead run (before a status report, before handing it an order, or when the lead looks stuck) without disturbing it.
---

# agenc-run-status

One read-only command replaces the ad-hoc peek scripts. It reads the supervisor, broker and budget-watch logs in `<meta-dir>`, the lead's session rollout under `<agenc-home>`, and `/proc`. It never writes, signals or calls the network.

## When to use
- Before any status report on a supervised lead run.
- Before handing the lead a new order (see [`agenc-order-lead`](../agenc-order-lead/SKILL.md)).
- When the lead looks stuck, silent, or is being relaunched.

## Command
```bash
python3 <skill-dir>/run_status.py --meta <meta-dir> [--agenc-home <agenc-home>] [--lines 3] [--wedge-min 10] [--json]
```
`--meta` defaults to `$AGENC_META`; `--agenc-home` to `~/.agenc`. Python 3.8+ standard library only.

## How to read it
- **SUPERVISOR**: pid from the last `[supervisor N]` line, alive via `/proc`, age of the last log line.
- **LEAD**: job, model, config, cwd from the last `launch <job> model <m> config <cfg>` line; relaunch and stall counts for the current supervisor only; launcher pid found by scanning `/proc/*/cmdline`.
- **SESSION**: the lead's rollout is the first `rollout-*.jsonl` created at or after that launch line in the project folder for the lead's cwd (children start later). Shows idle age, model calls, last agent message, last tool call, last error. `costUsd`/`heldCostUsd` here are AgenC estimates, not spend.
- **CHILDREN**: broker `launched` lines whose pid is alive and whose out dir has no `exit` file. `WEDGED?` means `out.jsonl` has been idle longer than `--wedge-min`. Also counts children finished since the lead launched, by exit code.
- **REAL SPEND**: last `usage=`/`delta=` line of the budget watcher and headroom to its STOP limit. This is the real number.
- **LAST LOG LINES**: the last N timestamped lines of each log.

## What to do with each signal (never touch the run)
1. Supervisor not alive: report it with the last supervisor lines. Do not relaunch it yourself unless a human asks.
2. Session idle longer than the wedge minutes and no live children: report "lead possibly wedged" with the idle age and last tool call. The supervisor or lead owns the kill; follow [`agenc-lead`](../agenc-lead/SKILL.md) step 3 and [`agenc-retry`](../agenc-retry/SKILL.md).
3. Child `WEDGED?`: report its role, pid and out dir to the lead (INBOX order) or the human. Do not kill it from outside.
4. Headroom low: say so and stop adding work; real limits per [`agenc-spend-guard`](../agenc-spend-guard/SKILL.md).
5. Last error is a provider retry (`stream_disconnected`, 429): usually transient; check again in a few minutes before reporting.

## Never
- Kill, signal, restart, or edit the supervisor, broker, lead or children.
- Touch `*.lock` files, the session sqlite, or anything in `<meta-dir>`.
- Quote `costUsd` from the SESSION section as spend.

## Why
Every relaunch of a long lead run, agents wrote a new throwaway peek script (five on one job) and still misread state: a size-based session pick showed a 70-minute-old session as current, and `token_count` was counted at the wrong nesting level (0 calls). This script fixes both and puts real spend next to the session.

## Sample (literal, trimmed; paths shortened)
```
SUPERVISOR:
  pid: 1841683
  alive: yes
  last timestamped line age: 2.2 min
LEAD:
  job: gf2-system-33
  model: minimax/minimax-m3.1-flash:free
  cwd: <worktree>
  relaunches (this supervisor): 5
  stalls (this supervisor): 5
  launcher pid: 2332163 (alive: yes)
SESSION:
  idle age: 2.4 min
  model calls (token_count): 27
  last session_usage: costUsd=244.077150001 heldCostUsd=48.9957 (AgenC ESTIMATE, not real spend)
  last agent_message: Now I understand the root cause. Let me check model pricing and the relay before dispatching.
  last error/stream_error: {'cause': 'stream_disconnected', 'message': 'provider error, retrying in up to 1 s (2/6): openrouter error: terminated', 'provider': 'openrouter'}
CHILDREN:
  (no live children)
REAL SPEND:
  last usage=7.746469727 delta=4.6629 watching: 1841683 1841692 2332163
  headroom to STOP: 6.3371
```
