---
name: journal
description: Read before the first journal entry of a task — which kind a line is, what closing one means, and which of them hold up the hand-over.
---

# The journal of a task

One append-only stream per task. An entry is never rewritten and never deleted; changing your
mind is a new entry pointing at the old one. What you *can* do later is **close** an entry —
once — by saying what settled it.

An entry has two halves. The **subject** (`title` + `body`) says what came up. The
**resolution** says what settled it. Open means the resolution is still empty.

## Four kinds, and the kind is the point

Pick by what the line *is*, not by how important it feels.

### `decision` — a choice you made, and what it rests on

The workhorse. Anything you settled along the way that someone could later ask "why is it like
this?" about.

Leave it **open** until it rests on something. That is not sloppiness — an open decision is
exactly what an assumption looks like here, and being able to see the assumptions is the whole
reason the kind exists. Close it when it acquires a foundation:

- the requester answered → the resolution is their answer;
- you went and checked → the resolution is the pointer to the check
  (`pytest -q → 12 passed`, `tariff.py:88 подтверждает`).

A decision that never acquires either is an assumption you shipped, and it will be visible.

### `finding` — something wrong or owed that you noticed elsewhere

A defect, a debt, a strangeness in code *outside* this task. Write it the moment you see it:
without somewhere to put it, it dies with the session and gets paid for again next time.

A finding does **not** hold up your hand-over. It is addressed to a person, who triages it in
their own order, and you have no way to close it — so it is not counted against you.

### `fact` — something to remember

A number, a path, an exact name, the reason something failed, a correction the requester made
in passing. Closed the moment it is written; it is waiting for nobody.

This is what survives a context compaction that a summary would smooth away. When in doubt about
an exact string, write it down.

### `remark` — the requester's word about your work

Not yours to write. You will see them in the journal and you close them, with what you did about
it. An entry whose halves are written by the same hand answers to nobody.

## What holds up the hand-over

`task_status(…, "in_review")` reports two numbers, and they are not the same:

- **blocking** — open `decision` and `remark`. Both are yours to settle: a decision needs its
  foundation, a remark needs your answer. Clear them before handing over.
- **open** — the above plus findings, which are the person's to triage.

## Attaching to a stage

`stage_code` says the entry came up in one step rather than in the task as a whole. Use it when
it is true — it is what lets someone reading a failed stage see what was going on inside it.
