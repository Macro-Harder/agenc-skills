---
name: xmodel-confirm
description: Use when an auditor or red team reports bugs and you want to know if a different model independently finds or confirms each one before acting on it.
---
# Cross-model bug confirmation

## Steps
1. Collect findings into a JSON list (or {"findings": [...]}) with id, severity, file, line, title, description, optional repro; or markdown "## id: title" sections with "- severity:", "- file:", "- line:", optional "repro:" lines. Note which model produced them.
2. Choose a check model from a different model family than the original (the script requires --model to differ from --original-model).
3. Run the script (usage below).
4. Read OUT/results.md.
5. Act per verdict.

## What the script does
Every model call (blind audit, judge, targeted check) runs as a headless `agenc -p --provider openrouter --model <id>` with read-only sandbox config, permission mode default, cwd set to the target code, a per-run call cap and deadline. Requires the `agenc` CLI on PATH. AGENC_MAX_OUTPUT_TOKENS comes from --max-tokens and reasoning effort from --reasoning-effort (passed as AGENC_EFFORT_LEVEL).

BLIND REDISCOVERY (one per target+perspective with mechanical prefilter same file and line within window then judge MATCH/NO_MATCH) and TARGETED CHECK (show finding plus code; model must CONFIRM with repro or REFUTE with counter-argument).

## Verdicts
- REDISCOVERED: check model found it independently in blind audit. Strong confirmation; prioritize.
- CONFIRMED_WHEN_SHOWN: confirmed after being shown the finding. Weaker than rediscovery.
- DISPUTED: refuted with counter-argument. Do not drop without human review or reproduction test.
- INCONCLUSIVE: an error or unclear answer. Rerun, or check it by hand or with a test.

## Usage
`python3 <skill-dir>/xmodel_confirm.py --findings <path> --target <path> --original-model <id> --model <id> --out <dir> [--judge-model <id>] [--perspective "..."] [--scope "..."] [--line-window 10] [--reasoning-effort minimal|low|medium|high|xhigh|max] [--max-tokens 4000] [--agent-timeout 900] [--task-max-calls 4] [--cost-settle-seconds 5] [--final-settle-seconds 60] [--max-code-chars 60000]`

The --out directory must be outside the target; the script never writes into the audited code.

Output: OUT/results.json and OUT/results.md (table: id | severity | file:line | title | verdict | blind | targeted). blind is MATCH, NO_MATCH, "no candidates" or error; targeted is CONFIRM, REFUTE, UNSURE or ERROR.

## Cost rule
The headline real cost is the OpenRouter key usage delta (GET /api/v1/key, data.usage) read at the start and after a settle wait at the end, from OPENROUTER_API_KEY in the environment. It can include other jobs running on the same key at the same time, so say so when you report it, and run alone on the key when exact numbers matter. AgenC's own cost figure is an estimate and is shown only as such; never report it as the cost. If cost_complete is false, say the real cost is unknown.

## Principles
- Model agreement is evidence, not proof. A failing reproduction test beats any number of agreeing models.
- DISPUTED still gets a human or test look before being dropped.
- REDISCOVERED outranks CONFIRMED_WHEN_SHOWN because seeing the finding anchors the checker.
