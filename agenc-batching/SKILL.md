---
name: agenc-batching
description: Use when many small independent asks would each pay the full prompt overhead; batch them into one run to pay the overhead once.
---
# Batch small asks to cut overhead

Every headless AgenC run carries a fixed prompt overhead: AgenC's built-in system prompt and tool list (inferred). In one measured run on AgenC 0.19.9, a prompt asking for one word sent about 6,000 prompt tokens and got 1 completion token back. So many tiny one-line runs mostly pay for overhead. Batch small asks into one run.

Checked against AgenC 0.19.9. Run `agenc help <command>` to confirm flags.

## 1. Measure the overhead

- Run one minimal call from an empty scratch dir. `<skills>` is where you copied these skill folders.
```bash
mkdir -p ./scratch
cd ./scratch
python3 <skills>/agenc-spend-guard/spend_guard.py run --limit 0.05 -- sh -c '
  AGENC_MAX_OUTPUT_TOKENS=200 agenc --provider <provider> --model <model> \
    --permission-mode plan --task-max-calls 3 --deadline +120 \
    --output-format json -p "Reply with the single word OK." > probe.json
  rc=$?; echo "agenc exit=$rc" >&2; exit $rc'
```
- Real cost = the settled usage delta the guard prints.
- Token counts come from AgenC's json output: one JSON object with `finalMessage`, `tokenUsage`, and an `events` list. The last `session_usage` event holds the run totals: `inputTokens`, `outputTokens`, `totalTokens`, `modelCalls`. `tokenUsage` has the same totals.
- Read them:
```bash
python3 -c 'import json; u = json.load(open("probe.json"))["tokenUsage"]; print(u["inputTokens"], u["outputTokens"])'
```
- `costUsd` there is an estimate (`costEstimated: true`). Never use it as the cost.
- Overhead per run ~= that delta. N separate runs cost about N x overhead + work; one batched run costs about 1 x overhead + work.

## 2. When to batch

- Tasks are small (short answer each, total expected output small vs the overhead), independent, same permission mode and same files/context, read-only or answer-only.
- When NOT to batch: tasks that edit code, need different scopes or permission modes, one failure should not void the rest, or the combined brief would be long enough that one bad result forces a full rerun.
- Keep batches to roughly 5-20 items; split bigger lists into several batches.

## 3. Batched brief template

- One goal, a numbered task list, and an output contract: a JSON array with one object per id.
- `status: "error"` instead of a missing item, so a gap always means a broken run.
```text
Goal: Answer the <N> numbered tasks below.
Answer each numbered task independently. Do not run commands or edit files.
1. <task>
2. <task>
<N>. <task>
Output: JSON only, no prose, no fences. An array of exactly <N> objects, ids 1..<N> in order, one per task:
[{"id": 1, "status": "ok|error", "answer": "<answer>"}, ...]
If you cannot do a task, keep its object and set "status": "error" with the reason in "answer". Never skip an id.
```

## 4. Run the batch

- Put the filled template in `./scratch/brief.md`.
- Wrap it as in [`agenc-spend-guard`](../agenc-spend-guard/SKILL.md) section 4.
```bash
cd ./scratch
python3 <skills>/agenc-spend-guard/spend_guard.py run --limit 0.10 -- sh -c '
  agenc --provider <provider> --model <model> \
    --permission-mode plan --task-max-calls 10 --deadline +300 \
    --output-format json -p "$(cat brief.md)" > batch.json
  rc=$?; echo "agenc exit=$rc" >&2; exit $rc'
```

## 5. Split results back out

- Take `finalMessage` from the json output and parse it as a JSON array.
- Check the length is N and the ids are exactly 1..N. Anything else: treat the whole batch as failed.
- Route each answer by id.
```bash
N=<N> python3 -c '
import json, os, sys
items = json.loads(json.load(open("batch.json"))["finalMessage"])
n = int(os.environ["N"])
if sorted(i["id"] for i in items) != list(range(1, n + 1)):
    sys.exit("bad batch: ids do not match 1..%d" % n)
for i in items:
    print("%s\t%s\t%s" % (i["id"], i["status"], i["answer"]))
'
```
- Rerun only the failed or missing ids in a new, smaller batch; this counts toward the retry limit in [`agenc-retry`](../agenc-retry/SKILL.md).

## 6. Report spend

- Report real spend for the batch (from the guard) and the per-task share = delta / N.
```text
Spend: $<delta> real for <N> tasks (provider usage delta, settled after <s>s); per task $<delta/N>
```
