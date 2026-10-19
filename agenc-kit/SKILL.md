---
name: agenc-kit
description: Use when an AgenC lead agent must ask its operator for a plugin, tool, connector or access it cannot install itself, record a skill or standing agent it made, or when the operator reads and grants those items, through a kit folder with INDEX.md.
---

# agenc-kit

A kit folder is the lead agent's mailbox to its operator and its record of what it built:
`skills/<name>/`, `agents/<name>/`, `requests/<name>.md`, and `INDEX.md` (`| type | name | status | date |`, status `active|retired|requested|granted`). Every item carries a four-part blurb: **What it is.** **What it does.** **Why it's needed:** (the real job or failure) **One idea to improve it** (optional). `kit.py` keeps the files and the index in step.

## Commands
```bash
K="--kit <kit-dir>"      # or export AGENT_KIT=<kit-dir>
python3 <skill-dir>/kit.py $K list                       # index + drift check; exit 2 on drift
python3 <skill-dir>/kit.py $K show <name>                # print one blurb
python3 <skill-dir>/kit.py $K request <name> --what "..." --does "..." --why "..." [--idea "..."] [--dry-run]
python3 <skill-dir>/kit.py $K add skill|agent <name> [--dry-run]   # index a folder already copied in
python3 <skill-dir>/kit.py $K status <name> granted|active|retired|requested [--dry-run]
```

## Lead agent: steps
1. `list` first. Fix any drift it prints.
2. Need something you cannot install? `request` it. `--why` names the real failure ("child runs fail with X because Y is missing"), not a wish.
3. Made a skill or a standing subagent (brief, profile, launcher)? Copy its folder into `skills/` or `agents/`, write `BLURB.md`, then `add`. `add` refuses a folder without a complete blurb.
4. Check `show <name>` later; `granted` means you may use it.

## Operator: steps
1. `list` to see open `requested` rows and drift.
2. Install or grant what is worth it, then `status <name> granted`. Say no by `status <name> retired` and a line in the request file on why.

## Rules
- Never delete an item; retire it.
- Edit INDEX.md only through the script (it appends rows and rewrites status atomically).
- Names are lowercase-hyphen slugs.
- No secrets in blurbs or requests.

## Why
A lead was told to record every red-team and blue-team agent it spawned in its kit. Hours and dozens of children later the kit's INDEX still had 0 rows, and nobody noticed because nothing checked it. `list` makes that drift visible in one line.

## Sample (literal)
```
$ kit.py --kit <kit-dir> list
0 INDEX row(s) in <kit-dir>/INDEX.md
OK: 0 skill(s), 0 agent(s), 0 request(s); INDEX matches disk
$ kit.py --kit scratch/kit list
3 INDEX row(s) in scratch/kit/INDEX.md
| request | agenc-run-status-access | granted | 2026-10-19 |
| agent | ghost | active | 2026-10-19 |
| skill | foo | active | 2026-10-19 |
DRIFT: 1 issue(s)
  INDEX agent ghost has no folder on disk
```

Related: [`agenc-lead`](../agenc-lead/SKILL.md), [`agenc-handoff`](../agenc-handoff/SKILL.md).
