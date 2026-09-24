---
name: task-plan
description: Read before planning a task — what goes in the plan as prose, what becomes a stage, and what counts as the proof that closes one.
---

# Planning the work

A task has two planning surfaces, and putting the wrong thing in each is the usual mistake.

**The plan** (`body`, edited with `body_set` and its neighbours) is prose: the approach, and
the files. **Stages** (`stage_add`) are the steps, each with its own state and its own proof.

## The plan is written after reading the code

Not before. That is why there is no `body` argument on `task_create` — at the moment a task is
created nothing has been read yet.

What makes a plan a plan rather than a promise: **it names the files**. The ones you read, and
the ones you are going to change. A plan without them is a paragraph of intent that nothing can
be checked against afterwards.

```
Подход: тариф считается в одном месте (tariff.py:Calculator), инвойс его только зовёт.
Меняю расчёт, не трогая формат счёта.

Прочитано: src/billing/tariff.py, src/billing/invoice.py, tests/billing/test_tariff.py
Меняю: src/billing/tariff.py, tests/billing/test_tariff.py
```

The limit refuses instead of trimming, and that is deliberate — the file list lives at the end,
so trimming would cut exactly the part worth keeping. If you hit it, the detail belongs in
stages, not in the plan.

## Stages belong to `extended` tasks only

That is the line between `standard` and `extended`, and it is the only one. A standard task keeps
its plan as prose in the body and nothing else; an extended one also breaks it into steps.

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

## Ahead of you the plan is alive, behind you it is frozen

A stage that has not started can be rewritten freely. A stage that is running or finished cannot
— the tools refuse it.

This is not tidiness. If the wording of a step can be adjusted after it has run, the gap between
what was promised and what was done disappears — and that gap is the only reason to keep a plan
at all. Changed your mind mid-flight? That is `note_add(type="decision")` saying why, and a new
stage after the one you are on.

## Evidence is a pointer, not a story

`stage_close` demands it, and it means: the thing someone else could go and look at.

- ✅ `pytest tests/billing -q → 12 passed`
- ✅ `src/billing/tariff.py:40-88, новый Calculator.apply`
- ✅ `alembic upgrade head → ok, integrity_check clean`
- ❌ «сделал», «работает», «всё ок»

The field is short on purpose: a command's full output does not belong in it, a pointer to the
command does. A step marked finished with no trace makes every step after it reason on a claim
nobody checked — and that failure is silent, which is what makes it expensive.

A cancelled stage takes evidence too. Why it was abandoned is worth the same line.

## Your own lifecycle vs the task's

Starting a stage does not start the task — they answer different questions. Move the task with
`task_status` when you actually pick it up, and hand it over at `in_review` when the stages are
closed. Whether the work is accepted is the requester's call; `done` is not yours to set.
