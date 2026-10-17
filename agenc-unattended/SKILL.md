---
name: agenc-unattended
description: Use when running AgenC from cron, CI, or any automation nobody is watching, so jobs stay capped, non-overlapping, logged, alerting, and never ship anything without human review.
---
# Run AgenC unattended

Nobody is there to answer a prompt, notice a loop, or stop a bad push. Every safeguard has to be in the command line and the wrapper.

Checked against AgenC 0.19.9. Run `agenc help <command>` to confirm flags.

## 1. Non-interactive rules

- **Print mode only.** `agenc ... -p "<brief>"`. Options go before `-p`; anything after it is prompt text.
- **Run from a project or scratch dir.** Never `$HOME`; it fails with `[sandbox_required_unavailable]`.
- **No approver exists.** Any tool that needs approval is denied (`Permission denied ... non-interactive one-shot: no approver`) and still costs a call. Write the brief so the agent never needs one.
- **Caps are mandatory.** Every run gets `--task-max-calls`, `--deadline +<seconds>`, and `--deadline-reserve <seconds>`. Add a token cap (`--budget` or `--task-token-budget`) and an outer `timeout` as a backstop.
- **Results to files.** `--output-format json > result.json 2> run.err`. Save `$?` immediately.

## 2. Permission modes

| Job | Mode | Notes |
|---|---|---|
| Read-only report, review, summary | `--permission-mode default` in an empty scratch dir, input pasted into the brief | Approval-gated tools are denied, so it stays read-only. `plan` also works but tends to spend calls on plan files; give it 15 or more. |
| Scoped edits | `--permission-mode acceptEdits` | Edits are allowed; shell commands can still need approval. Tell it not to run commands. The wrapper runs the checks. |
| Edits plus running tests | `--bypass-approvals` | Keeps the OS sandbox. Conflicts with `--permission-mode acceptEdits`. Refuses an untrusted directory (`project is not trusted`) until someone trusts it once by hand in a terminal, so it does not suit fresh CI checkouts. |

- **Never** use `--dangerously-bypass-approvals-and-sandbox`. Keep the sandbox on.
- Background agents: `agenc agent start --unattended-allow <tools> "<objective>"`. Grant the fewest tools the job needs, for example `--unattended-allow read,grep` for an audit. Check with `agenc agent list` and `agenc agent logs <id>`; stop with `agenc agent stop <id>`.

## 3. The agent never ships

- No pushes, merges, deploys, releases, tags, or messages from the agent.
- The job ends with a patch file or a branch for a human to review. If your automation opens a pull request, a separate step does it with a narrowly scoped token, after the checks pass; the agent never holds that token.
- Run in a fresh worktree or clean checkout. Never the deploy checkout.

## 4. Make every run safe to repeat

- **Lock.** One run per job at a time: `flock -n` on a per-job lockfile, or the CI system's concurrency group. A second firing exits quietly.
- **Job key.** Name each run by job and period, such as `nightly-lint-2026-10-17`. A key that already finished is skipped. A re-fired job does no duplicate work.
- **Separate state.** One worktree, result file, and log per job key and attempt. No two jobs write the same file. Merge results afterward, one at a time.
- **Fresh start.** Each attempt starts from a fresh worktree at the base ref, never from the last attempt's leftovers.

## 5. Verify inside the job

The agent's `RESULT: PASS` is a claim. The wrapper:
1. Checks the exit code is `0`.
2. Runs the done command itself in the worktree and saves the output.
3. Runs the mechanical review checks from [`agenc-review`](../agenc-review/SKILL.md) (`review_check.py`) in the same check command, and fails on findings.
4. Only then writes the patch and marks the key done.

## 6. Logs, results, and alerts

- Dated paths: `<state-dir>/<job-key>/result.<attempt>.json`, `agenc.<attempt>.err`, `check.<attempt>.log`, `change.patch`.
- Alert on every nonzero exit: AgenC failure, check failure, guard error, lock trouble. Silence means success, so a broken alert path is itself a failure; test it.
- Track real spend per job with [`agenc-spend-guard`](../agenc-spend-guard/SKILL.md). AgenC's `costUsd` is an estimate; never alert or bill on it.

## 7. Retries and escalation

Automation cannot sharpen a brief. Follow [`agenc-retry`](../agenc-retry/SKILL.md):
- Each scheduled firing is one attempt. At most 3 attempts per job key.
- Alert on each failure, with the exit code and log path.
- After the third failure, write an escalation note, alert a human, mark the key escalated, and exit nonzero. Later firings for that key exit nonzero without running until a human clears it.
- Never retry in a loop inside one firing. Never raise caps automatically.

Do not wait for a human on reversible work the job can check itself. Stop for anything irreversible.

## 8. Secrets

- Provider credentials come from the scheduler's or CI system's secret store, as env vars. AgenC reads the env var for your provider; `agenc providers --no-local-check` shows which providers have a usable credential.
- Never put keys in briefs, scripts, config files, or logs. Never echo them.
- Scope the key: a dedicated key per automation, with a spend limit at the provider if it supports one.

## 9. Daemon

- The daemon auto-starts on the first `-p` run and keeps running.
- On long-lived hosts, manage it yourself: `agenc daemon start|status|stop|restart`. Set `AGENC_DAEMON_AUTOSTART=0` in the job env so jobs do not start their own.
- A first call that hangs is often the daemon starting. Check `agenc daemon status` and `~/.agenc/daemon.log`.
- In CI, install with `--no-daemon` and let the run start it for the job's lifetime.

## 10. Cron wrapper

`agenc-cron.sh` (in this folder) does sections 4 to 7: lock, job key, fresh worktree, capped run, its own check, patch, alerts, 3 attempts then escalation. Exit `0` done or skipped, `1` failed (alerted), `2` config error, `3` escalated.

```bash
# Preview the commands without running anything:
JOB=nightly-lint REPO=/srv/repos/app BRIEF=/srv/briefs/nightly-lint.md \
CHECK="python3 -m pytest -q && python3 /srv/agenc-jobs/review_check.py --worktree . --base main --allow 'src/*'" \
PROVIDER=<provider> MODEL=<model> ./agenc-cron.sh --dry-run
```

crontab, nightly at 02:15:

```cron
15 2 * * * cd /srv/agenc-jobs && JOB=nightly-lint REPO=/srv/repos/app BRIEF=/srv/briefs/nightly-lint.md CHECK="python3 -m pytest -q" PROVIDER=<provider> MODEL=<model> ALERT_CMD="mail -s agenc-alert ops@example.com" AGENC_DAEMON_AUTOSTART=0 ./agenc-cron.sh >> /var/log/agenc-jobs/nightly-lint.log 2>&1
```

Put the provider key in the cron environment from your secret manager, not in the crontab line.

## 11. CI job

A generic GitHub Actions example. The same shape fits any CI: schedule, one-at-a-time concurrency, a job timeout, secrets from the store, artifacts for review, no push.

```yaml
name: agenc-nightly
on:
  schedule: [{ cron: "15 2 * * *" }]
  workflow_dispatch: {}
concurrency: { group: agenc-nightly, cancel-in-progress: false }
permissions: { contents: read }
jobs:
  run:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - name: Install AgenC (pinned)
        run: |
          curl -fsSL https://get.agenc.ag/install.sh -o /tmp/agenc-install.sh
          sh /tmp/agenc-install.sh --version 0.19.9 --no-daemon
          echo "$HOME/.local/bin" >> "$GITHUB_PATH"
      - name: Run job
        env:
          PROVIDER_API_KEY: ${{ secrets.PROVIDER_API_KEY }}   # map to the env var your provider expects
          JOB: nightly-lint
          JOB_KEY: nightly-lint-${{ github.run_id }}
          REPO: .   # the checkout
          BASE: ${{ github.sha }}
          BRIEF: .agenc-jobs/nightly-lint.md
          CHECK: python3 -m pytest -q
          PROVIDER: <provider>
          MODEL: <model>
          STATE_DIR: ${{ runner.temp }}/agenc-jobs
          MAX_ATTEMPTS: "1"   # CI state is fresh each run; track attempts outside CI if you retry
        run: ./.agenc-jobs/agenc-cron.sh
      - name: Keep results for review
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: agenc-nightly
          path: ${{ runner.temp }}/agenc-jobs/
```

A failed step fails the workflow, which is the alert. A human downloads `change.patch`, reviews it with [`agenc-review`](../agenc-review/SKILL.md), and applies it.
