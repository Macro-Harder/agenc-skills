---
name: agenc-spend-guard
description: Use when an AgenC job (or any metered agent job) must stay under a dollar limit and you need the real spend from your provider, not the agent's own estimate.
---
# Keep AgenC jobs under a dollar limit

Measure spend where the money is counted: your provider's usage endpoint. AgenC's `tokenUsage.costUsd` is an estimate and can be off by 100x or more. Never use it to enforce or report a limit.

Checked against AgenC 0.19.9. Run `agenc help <command>` to confirm flags.

## 1. Know the number before you trust it

- **Source.** Real spend is the change in cumulative usage on your provider's usage or key endpoint. Nothing else.
- **Lag.** Usage can trail the job by a minute or more. A read taken right after the job often shows zero. Wait and read again.
- **Shared key.** The endpoint counts every job on that key. Run metered jobs one at a time per key, or give each job its own key, or the delta mixes jobs.
- **Limiter.** Before you report a number, name what produced it: one job's delta after usage settled, on a key nothing else was using. If you cannot name that, report the number as unconfirmed.

## 2. Configure the guard

`spend_guard.py` (in this folder, Python standard library only) reads one number from a JSON usage endpoint.

| Setting | Flag | Env | Default |
|---|---|---|---|
| Usage URL | `--url` | `PROVIDER_USAGE_URL` | none |
| JSON path to cumulative USD | `--json-path` | `PROVIDER_USAGE_PATH` | `data.usage` |
| Name of the env var holding the key | `--key-env` | `SPEND_GUARD_KEY_ENV` | `PROVIDER_API_KEY` |
| Snapshot file | `--state` | `SPEND_GUARD_STATE` | `~/.local/state/spend-guard/snapshot.json` |

- The key goes out as `Authorization: Bearer <key>`. The guard never prints it or writes it to the snapshot.
- Global flags go before the subcommand: `spend_guard.py --state day.json check --limit 5`.

```bash
export PROVIDER_USAGE_URL='https://<provider>/<usage-endpoint>'
export PROVIDER_USAGE_PATH='data.usage'
```

## 3. Snapshot and check

```bash
python3 spend_guard.py snapshot
# ... run jobs ...
python3 spend_guard.py check --limit 0.50
```

Output is one line: `start=... now=... delta=... limit=... ok|OVER`.

Exit codes:
- `0` within the limit.
- `10` over the limit.
- `11` guard error: no URL, empty key, unreachable endpoint, bad JSON path. Treat it as a stop, not a pass.

## 4. Wrap one job

```bash
cd /tmp/scratch-job
python3 spend_guard.py run --limit 0.25 -- sh -c '
  agenc --provider <provider> --model <model> \
    --permission-mode plan --task-max-calls 15 --deadline +600 \
    --output-format json -p "$(cat brief.md)" > /tmp/job.json 2> /tmp/job.err
  rc=$?; echo "agenc exit=$rc" >&2; exit $rc'
```

`run` does this:
1. Snapshots usage.
2. Starts the command in its own process group.
3. Reads usage every `--poll` seconds (default 15). If the delta passes the limit, it stops the whole group.
4. After the command exits, polls until usage moves and holds steady, up to `--settle` seconds (default 120).
5. Prints the real delta.

Exit codes: the command's own exit code, `10` if over the limit, `11` on a guard error.

- Use `sh -c '...'` so redirects apply to the agent, not the guard.
- Save `rc=$?` before any other command, or you report the wrong exit code.
- Mid-run stopping is best effort. Usage lag means a job can overshoot before the guard sees it. Caps inside the run are the hard stop; the guard is the backstop.
- If it prints `usage did not move`, the number is not final. Run `check` again later before reporting.

## 5. Layer the limits

Set every layer. Each catches what the others miss.

| Layer | Stops | Set with |
|---|---|---|
| Call cap | runaway loops | `--task-max-calls <n>` |
| Token cap | huge contexts | `--budget eco\|balanced\|max` or `--task-token-budget <tokens>` |
| Deadline | hangs and slow loops | `--deadline +<seconds>` (exit 5) |
| Run USD cap | durable runs | `agenc run start ... --max-cost <usd>` |
| Real per-job limit | estimate drift | `spend_guard.py run --limit <usd>` |
| Real per-day limit | many small jobs | a daily snapshot plus `check` |

`--max-cost` relies on AgenC's own accounting. Keep the real per-job limit on top of it.

Even trivial tasks take several model calls. A cap of 2 or 3 fails on simple work. Start near 10 for small tasks and raise it once if the run ends with `reached its N model-call limit`.

Every run also pays a fixed prompt overhead. Batch small asks: see [`agenc-batching`](../agenc-batching/SKILL.md).

## 6. Per-day limits

Take one snapshot per day per key, then check it before each job:

```bash
# once a day, e.g. from cron at 00:00
python3 spend_guard.py --state ~/.local/state/spend-guard/day.json snapshot

# before each job
python3 spend_guard.py --state ~/.local/state/spend-guard/day.json check --limit 5.00 \
  && python3 spend_guard.py run --limit 0.25 -- sh -c '...'
```

Per-job `run` writes its own snapshot to the default state file. Keep the daily snapshot in a separate file so jobs never overwrite it.

## 7. When a limit trips

- Exit `10` from `run`: the job cost more than allowed. Do not rerun it with a higher limit. Read the result first, then sharpen or split the brief (see [`agenc-retry`](../agenc-retry/SKILL.md)). A rerun counts toward the same 3-attempt limit.
- Exit `10` from the daily `check`: stop all jobs on that key for the day and tell a human.
- Exit `11`: fix the guard config. Never run unguarded because the guard is broken.
- AgenC reports `request is too large for the current allowance`: set `AGENC_MAX_OUTPUT_TOKENS=4000` (or lower) in the job's env.

## 8. Report spend

Report the settled delta from the guard, the job it covers, and whether usage had settled. Never report `costUsd` from AgenC output, and never print the key.

```text
Spend: $0.0097 real (provider usage delta, settled after 50s, key used by this job only)
```
