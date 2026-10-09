# tools

Scripts for operating an installation that serve not the application but the person next to it: seed
the database, look at the interface with live data, reproduce a scenario. The application imports
nothing from them — the reverse direction, `tools/` → `src/`, is the only one allowed.

## seed_demo.py

Demo data for the `tasks` module: three workspaces, seven groups and some fifteen tasks covering
every type, status, priority, stages and the journal. Meant for debugging the interface — an empty
list shows no sections, no branches and no trash.

```bash
uv run python tools/seed_demo.py            # three workspaces, the full set
uv run python tools/seed_demo.py --small    # only "Demo: development"
```

Writes to the database from `.env` — the same one the application sees. **Inserts only**: the script
deletes nothing, and every run adds a new set of workspaces prefixed "Demo:". To clean up, use the
interface: "Workspaces" → delete → "Delete forever" (the cascade takes the groups, tasks, stages and
journal with it).
