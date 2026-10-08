---
name: task-brief
description: Read before writing or filling in a task brief — a goal, context, constraints and criteria that someone else can act on without asking you what you meant.
---

# Setting a task someone else will run

A brief is not a title with an explanation. Whoever runs the task will not catch you in the
corridor and will not sense that a sentence reads oddly — everything left implicit gets filled
in, and it gets filled in toward the shortest path to something that *looks* finished.

Four fields, and each answers a different question.

## Goal — `description`

**What becomes true when the work is done.** An outcome, not a sequence of steps.

- ✅ «Invoices are issued under the new tariff scheme, the old ones do not break»
- ❌ «Open tariff.py, find the class, add a field» — this turns the executor into a slow
  typist and moves the whole design risk onto you.

If the approach is already decided, that is a constraint, not a goal. Keep them apart: the goal
says what must be true, the constraint says what you have already ruled out.

## Context — `context`

**Pointers to what the code does not say.** The code will be read; the reasons will not.

Three things are worth writing, and little else:

- where to start reading;
- which existing implementation is the reference to copy;
- a decision that is not visible in the repository, and why it went that way.

Pointers, not pasted text. A path and a line number beat a quoted fragment that will drift.

## Constraints — `constraints`

Three lists, and the third is the one people forget.

| | |
|---|---|
| Always | the defaults — which logger, where tests go |
| Ask first | changing a table, adding a dependency |
| Never | do not delete tests, do not touch the payments module |

Without an explicit «never», the executor will add whatever it thinks is needed, and the
tempting refactor next door arrives inside a risky change.

## Criteria — `criteria`

**The only thing separating "done" from "looks done".** One requirement per line, each
checkable on its own, each with what proves it.

The test of a criterion: could two readers disagree about whether it is met? If yes, it is not
finished being written.

- ✅ «1. `pytest tests/billing -q` is green»
- ✅ «2. The March invoice recalculates to the same cents — checked against three examples from prod»
- ❌ «Works reliably» — read as already satisfied.
- ❌ «Loads fast» — say the number and the conditions.

Do not write twenty-five of them. Past a certain length they stop producing care and start
producing selective compliance; five that matter beat twenty that do not.

## Which fields a task actually needs

`simple` — a title, a goal and the context: what to know before starting. No constraints, no
criteria, no plan, no journal. Often a job for a person rather than for you.
`standard` — the four fields above, a plan written as prose, and a journal. The normal profile.
`extended` — the same plus **stages**: the plan broken into steps, each with its own state and
its own evidence. That is the whole difference, and it is a real one — a step is a thing you can
be part-way through, and tracking that only pays off when the work outlasts one sitting. Reach
for it when a wrong assumption would be expensive to discover late; on a two-hour task the
ceremony costs more than it returns.

## Whose brief is it

You may fill in and correct the brief of any task with `task_update`, including one a person
set. A thin statement — a title and a goal — is often left on purpose for the executor to flesh
out once the code has been read.

On a task a person set, the brief is still their statement of what "done" means, so the edit
must not be silent: record what changed and why with `note_add(type="decision")`. If the
change is not a clarification but a different requirement, ask before making it.

Write the brief into the task, never into a file of your own to be copied over later.
