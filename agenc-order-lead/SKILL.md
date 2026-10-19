---
name: agenc-order-lead
description: Use when a running AgenC lead must get a new order or rule without a restart; append it, tagged, to every copy of its job docs (INBOX.md and DECISIONS.md) and confirm from its session rollout that it read it.
---

# agenc-order-lead

A running lead reads its job docs between units. You give it an order by appending to them, never by touching its process. `order_lead.py` does the append in every copy at once, tags it, and later proves the lead saw the tag.

## Steps
1. **Find every copy.** The lead prompt names the INBOX path it reads; the canonical job folder is usually a second copy. Pass each as `--job-dir`. An order missing from the copy the lead reads was never sent.
2. **Check state first** with [`agenc-run-status`](../agenc-run-status/SKILL.md). If the lead is dead or wedged, the order waits; say so.
3. **Write one order.** One section, short imperative bullets, ending with a done-check ("reply in DECISIONS.md with ..."). Put it in a file for anything over a line.
4. **Dry-run:**
   ```bash
   python3 <skill-dir>/order_lead.py send --job-dir <job-dir> --job-dir <run-copy> \
     --from <sender> --title "<title>" --body-file order.md --dry-run
   ```
   Read the WARNING lines. Diverged copies mean an earlier append reached only one of them.
5. **Send** with the same flags minus `--dry-run`, plus `--sessions '<agenc-home>/projects/<project>/sessions/*/rollout-*.jsonl'`. It appends (never rewrites), re-reads each file for the tag, saves a receipt with current session sizes under `~/.local/state/agenc-order/`, and prints the tag. Exit 1 means some copy failed: fix that before relying on the order.
6. **Confirm** after the lead's next unit:
   ```bash
   python3 <skill-dir>/order_lead.py confirm --tag ORDER-<stamp> --sessions '<same glob>'
   ```
   It scans only what each session wrote after the send (from the receipt), plus any session created later (a relaunched lead).
   - `0 CONFIRMED`: the tag appeared in the lead's tool output or messages.
   - `3 READ-NOT-SEEN`: the lead read INBOX.md but not your section (it read a tail or head that cut it off). Keep orders short and at the end; tell it the tag in the title.
   - `4 NOT YET`: no read since the send. Check again after the next unit; if it stays 4, check status. Never restart the lead to force a read.
7. **Report** the tag, the files, and the confirm result.

## Rules
- Append only. Never edit or reorder earlier INBOX sections or DECISIONS lines.
- Never write into the lead's sandbox, session files, or the supervisor's control files.
- Never signal, kill or restart the lead to deliver an order.
- An order a human gave goes in their words; quote them.

## Why
On a real job the two DECISIONS.md copies had drifted to 87,916 vs 31,572 bytes because appends reached only one copy, and nobody could tell whether the lead had read a given order. The tag plus saved offsets turns "I wrote it" into "it saw it".

## Sample (literal, scratch copies)
```
WARNING: DECISIONS.md copies differ in size
Tag: ORDER-20261019-143951
scratch/a INBOX: OK
scratch/a DECISIONS: OK
scratch/b INBOX: OK
scratch/b DECISIONS: OK
Receipt: scratch/receipts/ORDER-20261019-143951.json (1 session offsets)
$ order_lead.py confirm --tag ORDER-20261019-143951 --sessions 'scratch/rollout-*.jsonl'
Scanning 1 session file(s); receipt found
READ rollout-old.jsonl +1 tool_call_started: {"cmd":"tail -40 /x/INBOX.md"}
TAG  rollout-old.jsonl +2 tool_call_completed: ... <sender>: Scratch test order [ORDER-20261019-143951]\n- scratch only"}}}}
CONFIRMED: the lead saw ORDER-20261019-143951
```

Related: [`agenc-lead`](../agenc-lead/SKILL.md), [`agenc-handoff`](../agenc-handoff/SKILL.md), [`agenc-escalate-to-lead`](../agenc-escalate-to-lead/SKILL.md).
