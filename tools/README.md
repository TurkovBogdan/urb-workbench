# tools

Scripts for operating an installation that serve not the application but the person next to it: seed
the database, look at the interface with live data, reproduce a scenario. The application imports
nothing from them — the reverse direction, `tools/` → `src/`, is the only one allowed.

## seed_demo.py

Demo data across the modules: six workspaces (one empty, one in the trash), some twenty-five tasks
covering every type, status, priority, stages, the journal and task notes, and eight codexes with
their note trees mounted into the workspaces — one tree at the depth limit, one codex without notes,
one switched off in a workspace, one deleted. Meant for debugging the interface — an empty list
shows no sections, no branches and no trash.

On top of that, `seed_demo_bulk.py` generates the long texts and the volume: a workspace whose task
fields sit near their caps (notes up to ~63 000 characters, sixteen journal entries, ten long
stages), a workspace with some 125 tasks across eight groups, and a handbook codex of ~100 long
notes. The texts are composed from a seeded library, so every run produces the same ones.

```bash
# every codex and eight workspaces, the bulk included
uv run python tools/seed_demo.py
# the hand-written codexes and only "Demo: development"
uv run python tools/seed_demo.py --small
# only the bulk — mounts the hand-written codexes already in the database instead of adding them again
uv run python tools/seed_demo.py --bulk
```

Writes to the database from `.env` — the same one the application sees. **Inserts only**: the
script's own deletes only put its own fresh rows in the trash, and every run adds a new set of
workspaces prefixed "Demo:" and codexes with a `-2`, `-3`… segment suffix. To clean up, use the
interface: "Workspaces" → delete → "Delete forever" (the cascade takes the groups, tasks, stages,
journal and mounts with it), and the codexes from the "Codex" page.
