---
name: agenc-cli
description: Use when you need to run the AgenC coding-agent CLI headless (repo edits, test runs, code review, refactors, background agents) and want the verified flags, permissions, output formats, and fixes for common failures.
---
# AgenC CLI (coding agent)

Verified against `agenc 0.19.9` (`~/.local/bin/agenc`, home `~/.agenc`, standalone installer) on 2026-10-17. Auto-updates are on, so re-check `agenc --version` and `agenc help <cmd>` if a flag misbehaves.

## 1. Install check
```bash
agenc --version
agenc doctor
agenc providers --no-local-check   # which providers have usable credentials
agenc daemon status
```
A provider listed `Usable: no` has no credential. Do not try to fix that by reading key files.

If `agenc` is missing: `curl -fsSL https://get.agenc.ag/install.sh -o /tmp/agenc-install.sh`, read it, then run it. The npm package needs a recent Node; the standalone installer bundles its own.

## 2. Headless invocation
**Put all options BEFORE `-p` and the prompt.** Anything after the first positional token becomes prompt text, so a trailing `--provider` is silently ignored and the default model is used.
```bash
agenc --provider <provider> --model <model> --task-max-calls 10 -p "Summarize src/ in 5 bullets"
agenc --model <provider>:<model> --output-format json -p "List failing tests" > out.json   # also text | stream-json
agenc -p -- "--flag is literal text"
```
- **cwd = project.** `cd` into the repo or a scratch dir first. Launching from `$HOME` fails with `[sandbox_required_unavailable]`.
- **Files out:** the agent writes inside the cwd; capture the answer with stdout redirection or `--output-format json`. It may leave empty `.git`, `.agenc`, `.agents` dirs in the cwd; prefer a scratch dir under `/tmp`.
- Cap run time with `--deadline +600` (exit 5 on deadline) and `--deadline-reserve <s>`.
- Exit codes: 1 fail, 2 denied/bad option, 3 review required, 4 empty, 5 deadline.
- Verified-change work: `agenc run start --goal "<text>" --cwd <repo> --max-cost <usd> --verify "tests=npm test" --follow`, then `agenc run status|result|cancel <run-id>`.

## 3. Provider and model flags
- `--provider <name>` overrides the provider for the session; `--model <id|provider:id>` overrides the model. `--model <provider>:<model>` sets both in one flag.
- `agenc providers --no-local-check` lists each provider's default model and whether a credential is present. Credentials come from the env var your provider uses; keep it in your secret store.
- Unflagged runs fall back to the config default (`agenc config show`). Always pass both flags explicitly.
```bash
cd /tmp/agenc-scratch
AGENC_MAX_OUTPUT_TOKENS=4000 agenc --provider <provider> --model <model> \
  --task-max-calls 10 --deadline +600 -p "..."
```

## 4. Output, config and cost reporting
- `--output-format text|json|stream-json` (print mode). `json` returns the event stream including `session_usage`.
- `agenc config show|get|set|unset|validate|path`; user config is `~/.agenc/config.toml`. `agenc init` creates project `.agenc/config.toml` and `AGENC.md`. Use `--config <path>` or `--profile <name>` for a one-off layer.
- **max_tokens trap:** AgenC can ask the provider for the model's full output window. With a small credit balance the provider answers 402 and AgenC shows `This hosted model request is too large for the current allowance`. Set `AGENC_MAX_OUTPUT_TOKENS=4000` (or similar) in the env to fix it.
- **AgenC's cost estimate is wrong**, often by 100x or more. Record real spend from your provider's usage endpoint, before and after the run, printing only usage numbers (see [`agenc-spend-guard`](../agenc-spend-guard/SKILL.md)):
```bash
curl -s "$PROVIDER_USAGE_URL" -H "Authorization: Bearer $PROVIDER_API_KEY" \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["usage"])'
```
  Usage can lag by a minute or more. A key limit is not the account balance; a 402 means account credits are low.

## 5. Budget and limits
- `--task-max-calls <calls>` caps model calls per task (0 disables). A run that ends with `reached its N model-call limit` and 0 tokens failed on the first call; read the error, do not just raise the cap.
- `--budget eco|balanced|max` sets the task token budget (1M, 2.4M, unlimited); `--task-token-budget <tokens>` overrides.
- `agenc budget status` shows daemon admission policy, which is **off by default**, so per-task flags are the real guard.
- `agenc run start ... --max-cost <usd>` sets a hard USD cap for durable runs.

## 6. Permissions
- `--permission-mode default|plan|acceptEdits|bypassPermissions`. Use `plan` for read-only analysis, `acceptEdits` for scoped edits in a scratch or worktree dir.
- `agenc permissions list|approve|revoke` manage rules.
- `--bypass-approvals` keeps the OS sandbox. **Never** use `--dangerously-bypass-approvals-and-sandbox`.
- `agenc security audit` checks exposure (exit 1 on critical).

## 7. MCP basics
```bash
agenc mcp list | get <name> | remove <name>
agenc mcp add -t stdio -e KEY=value <name> <command> [args...]
agenc mcp doctor
```
Pass secrets via `${NAME}` env interpolation, never literal values.

## 8. Daemon
Auto-starts on the first `-p` (disable with `AGENC_DAEMON_AUTOSTART=0`). `agenc daemon status|start|stop|reload|restart`. Log: `~/.agenc/daemon.log`. Don't delete `daemon.sock` by hand.

## 9. Troubleshooting
| Symptom | Fix |
|---|---|
| Ran on the default model / 404 instead of the chosen provider | Move `--provider/--model` before `-p` |
| `request is too large for the current allowance` / 402 | Set `AGENC_MAX_OUTPUT_TOKENS=4000`; check account credits |
| `native secure storage is unavailable ... libsecret` | Expected; rely on env keys |
| `[sandbox_required_unavailable]` | Launched from `$HOME`; `cd` into a project dir |
| Hangs on first call | Daemon starting; check `daemon status` and `daemon.log` |
| Tool denied in background agent | Add it via `--unattended-allow` at start |
| `Permission denied ... non-interactive one-shot: no approver` in `-p` events | Headless runs deny approval prompts; brief the agent not to call that tool (see [`agenc-retry`](../agenc-retry/SKILL.md)) |
| Differs from docs | Run `agenc help <cmd>` |

## 10. Safety
- Never print, echo or log API keys; redact them in anything you relay.
- No production deploys, pushes, credential handling or infra changes through AgenC. Code and analysis in scratch/worktree dirs only; review the diff yourself before anything ships.
- Always cap with `--task-max-calls`, plus `--deadline` for unattended jobs.
- Keep the sandbox on.
