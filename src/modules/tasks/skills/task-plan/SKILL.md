---
name: task-plan
description: Read before planning a task — what goes in the plan, the progress diary and the result, what becomes a stage or a task note, and what counts as the proof that closes a stage.
---

# Planning the work

Your work on a task is written in three fields, one question each, in the order the work goes:

| Field | Answers | Written |
|---|---|---|
| `plan` | how you will do it — the approach and the files | after reading the code, before changing it |
| `progress` | how it is going — a diary, an entry at a time | along the way |
| `result` | what came out — what changed, what checked it, what is left unchecked | at hand-over |

All three are edited with `content_set` / `content_replace` / `content_set_section` /
`content_add`, the field named in the second argument. **Stages** (`stage_add`) are the plan
broken into steps, each with its own state and its own proof. Putting the wrong thing in each
place is the usual mistake: a plan that narrates the course, a diary that re-plans, a result
that retells the diary.

## The plan is written after reading the code

Not before. That is why there is no `plan` argument on `task_create` — at the moment a task is
created nothing has been read yet.

What makes a plan a plan rather than a promise: **it names the files**. The ones you read, and
the ones you are going to change. A plan without them is a paragraph of intent that nothing can
be checked against afterwards.

```
Approach: the tariff is computed in one place (tariff.py:Calculator), the invoice only calls it.
I change the calculation without touching the invoice format.

Read: src/billing/tariff.py, src/billing/invoice.py, tests/billing/test_tariff.py
Changing: src/billing/tariff.py, tests/billing/test_tariff.py
```

The limit refuses instead of trimming, and that is deliberate — the file list lives at the end,
so trimming would cut exactly the part worth keeping. If you hit it, the detail belongs in
stages, not in the plan.

## Progress is a diary, appended to

One or two lines per entry: what is done, what comes next. Append with
`content_add(code, "progress", text, "end")`, carrying the newline yourself.

```
- Migration bil_005 written, rollback checked → CRUD next.
- List response breaks on the old field → investigating.
```

It is not the journal. A choice and its reason is a `decision`, a defect elsewhere is a
`finding`, an exact number is a `fact` — `journal_add`. The diary says where the work is; the
journal says why it is shaped that way.

## The result is written at hand-over

Before `task_status(…, "in_review")`, say what came out in `result`: what changed, what checked
it, what is left unchecked. Short — the story of the work is in the progress, and the person
reads the result first.

## A note holds what the plan cannot

Some planning produces material rather than steps: a data schema, a comparison of three options,
a concept with a diagram, a table you will come back to. Put that in a **task note** —
`task_note_add(task_code, title, description, body)` — and point at it from the plan by its
`NOTE@` code. The plan stays the approach and the files; the note is what the approach rests on,
and the task page shows the notes right under the plan.

A note is planning material, not a planning step: it is written whenever the work needs it — at
any stage, after the plan too — and always when the user asks for one.

- A paragraph the plan can hold is not a note. A note earns its place when it has sections,
  a diagram or a table, or when someone will open it on its own.
- The `description` is what a reader decides by — `task_get` lists the task's notes by title and
  description only. Say what the note is about and when to open it.
- The text is content: `content_set(code, "body", …)` and its neighbours edit it in place;
  `task_note_update` renames it; `task_note_get` reads it whole.
- A note belongs to its task alone. Any task type keeps notes, a `simple` one included.

## Stages belong to `extended` tasks only

That is the line between `standard` and `extended`, and it is the only one. A standard task keeps
its plan as prose in `plan` and nothing else; an extended one also breaks it into steps.

So the type is a judgement about the work, not about how carefully you intend to write: choose
`extended` when the work outlasts one sitting and "where am I, and what proves the part behind
me" becomes a real question. On anything shorter the prose plan answers it already, and
`stage_add` on a standard task refuses rather than pretending.

## A stage is one step done in one go

As soon as a step needs its own acceptance — someone else has to look at it and say yes — it is
not a stage but a subtask. Create it with `task_create(parent_code=…)`.

The tree is one level deep: a subtask has no subtasks of its own. If the task you are running is
itself a subtask, the new piece goes next to it — under the same parent — not under it.

**Numbers order the plan, they do not count it.** Deleting a stage leaves a gap, and the gap is
fine. Do not renumber to close it: you refer to "the third stage" in the journal, and a silent
shift makes those references false.

## Changing course is said, not re-worded

No tool freezes a stage: its body stays editable on any status, and so does the plan. Clarifying
a step's wording is fine. Changing what a step behind you promised is not a clarification — the
gap between what was promised and what was done is what a plan is kept for, and re-wording it
after the fact erases the gap. Changed your mind mid-flight? That is `journal_add(type="decision")`
saying why, and a new stage after the one you are on.

## Evidence is a pointer, not a story

`stage_close` demands it, and it means: the thing someone else could go and look at.

- ✅ `pytest tests/billing -q → 12 passed`
- ✅ `src/billing/tariff.py:40-88, new Calculator.apply`
- ✅ `alembic upgrade head → ok, integrity_check clean`
- ❌ «done», «works», «all good»

The field is short on purpose: a command's full output does not belong in it, a pointer to the
command does. A step marked finished with no trace makes every step after it reason on a claim
nobody checked — and that failure is silent, which is what makes it expensive.

A cancelled stage takes evidence too. Why it was abandoned is worth the same line.

## Your own lifecycle vs the task's

Starting a stage does not start the task — they answer different questions. Move the task with
`task_status` when you actually pick it up, and hand it over at `in_review` when the stages are
closed. Whether the work is accepted is the requester's call; `done` is not yours to set.
