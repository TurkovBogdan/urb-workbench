# core/scheduler

Background task scheduler: a fixed-step ticker, a module-global registry, owner-based automatic lock release, heartbeats and cleanup of zombie runs.

## Where tasks are registered

Convention: handlers and their registration live in `tasks.py` or a `tasks/` package next to the code that executes them:

- core — `src/core/tasks.py`, registered from `app_factory.create_app`.
- module — `src/modules/<name>/tasks.py` or `src/modules/<name>/tasks/<task>_task.py`, registered from the module's `register(app, settings)`.

`module` in `scheduler.register` is the full module name (`"headhunter"`, not `"hh"`).

## Registering a task

Each task is a static class with `register()` and `handle()`:

```python
from src.core import scheduler
from src.core.scheduler import TaskContext


class SyncVacanciesTask:
    """One vacancy sync run."""

    @staticmethod
    def register() -> None:
        scheduler.register(
            module="headhunter",
            code="sync_vacancies",
            name="Vacancy sync",
            description="Every 5 minutes pulls fresh vacancies from the hh.ru listing.",
            schedule="*/5 * * * *",   # standard 5-field cron
            handler=SyncVacanciesTask.handle,
            ttl=300,                   # seconds; both the handler timeout and the task lock TTL
            enabled=True,              # false → the ticker skips the task
            manual_run=False,          # true → the task can be run by hand from the UI
        )

    @staticmethod
    async def handle(ctx: TaskContext) -> None:
        await ctx.info("syncing")
        # ... work ...
```

Through `CoreTaskBase` (the declarative variant):

```python
from src.core.scheduler import CoreTaskBase, TaskContext


class SyncVacanciesTask(CoreTaskBase):
    MODULE = "headhunter"
    CODE = "sync_vacancies"
    NAME = "Vacancy sync"
    DESCRIPTION = "Every 5 minutes pulls fresh vacancies from the hh.ru listing."
    SCHEDULE = "*/5 * * * *"
    TTL = 300
    ENABLED = True
    MANUAL_RUN = False  # optional; False by default

    @staticmethod
    async def handle(ctx: TaskContext) -> None:
        await ctx.info("syncing")
```

- **`schedule`** — a standard 5-field cron (`minute hour dom mon dow`). The finest granularity is once a minute. `None` — automatic runs disabled (the ticker skips the task; it can only be run by hand).
- **`ttl`** — an integer number of seconds. Used both as the `asyncio.wait_for` timeout and as the task lock TTL.
- **`enabled`** — the activity flag; `false` disables the task at the registry level (the ticker skips it while walking the registry and writes nothing to `core_tasks`).
- **`manual_run`** — permission to run by hand through the UI/API (`POST /api/core/tasks/{module}/{code}/run`). A declarative flag: `run_entry` is safe to call from anywhere, the flag only signals the UI and protects the endpoint. Defaults to `False`.
- **`sort`** — an integer that sets the display order of tasks in the UI (lower → earlier). Does not affect execution. Defaults to `500`.
- `(module, code)` is unique in the registry. Registering twice raises `ValueError`.

### Pattern: manual run only

A task without a schedule — `schedule=None, manual_run=True`. The ticker ignores it; the UI shows a "Run" button.

```python
class ReindexTask(CoreTaskBase):
    MODULE = "search"
    CODE = "reindex"
    NAME = "Reindex"
    DESCRIPTION = "Manual full rebuild of the index."
    SCHEDULE = None       # never run automatically
    TTL = 600
    MANUAL_RUN = True     # allow running from the UI
```

## What the handler sees — `TaskContext`

```python
@dataclass
class TaskContext:
    task_id: int
    module: str
    code: str
    lock: CoreLock          # task-level lock: key "task:{module}:{code}", owner=task_run:{id}
```

- `ctx.{debug,info,warn,error}(msg, *args)` — writes to `core_tasks_logs` and copies to the `tasks` channel (`logs/tasks.log`). Every call gets its own session with an immediate commit, so the log survives the task being dropped on TTL. Accepts `%`-args. DB write errors are swallowed — logging never crashes the handler.
- `ctx.set_payload(payload)` — updates `core_tasks.payload` in a fresh session with an immediate commit.
- `ctx.lock` — the task-level `CoreLock` instance taken by the runner. The handler may call `ctx.lock.is_owner()` / `ctx.lock.extend(ttl)` (e.g. for long tasks that extend it on heartbeat).

### Sub-locks under the same owner

If a task wants locks on resources internally (`hh:sync`, `pdf:render`, etc.), it takes them through `CoreLock.acquire(...)`, passing `owner=ctx.lock.owner`. The runner then releases everything in `finally` with one `release_for_owners`:

```python
async def sync_vacancies(ctx):
    res = await CoreLock.acquire("hh:api", 60, owner=ctx.lock.owner)
    if res is None:
        return  # the resource is busy
    # ... work; no need to call release — the runner cleans up ...
```

## Lifecycle

`scheduler.start(config)` starts the `Ticker`; `scheduler.stop()` stops it. Both are called from the app factory's `lifespan`. Where the parameters come from, and whether it starts at all, depends on the process role:

- **Embedded (dev, `--backend --worker`):** starts according to `config.worker_enabled`; scope/knobs come from `config` (`worker_modules_set`, `worker_tick_seconds`, `worker_max_concurrent_runs`). One process carries both the web and the tasks.
- **Pure worker (`--worker` without `--backend`):** the `src/app.py` entry point calls `scheduler.configure_worker(modules, max_concurrent, tick)` BEFORE the lifespan — this forces the ticker to start (bypassing `worker_enabled`) and sets the scope. The process has no uvicorn/port; the lifespan is driven directly.

The process role is a composition of the `--backend`/`--worker` flags (precedence flag > env > default); see [`dev/docs/ENV.md`](../../../dev/docs/ENV.md).

Settings in `Config`:
- `WORKER_ENABLED` (default `false`) — the embedded scheduler inside the web backend. `true` in dev (one process carries web + tasks); a production web process keeps `false` — background work runs in a separate worker process. `false` in tests. A pure worker forces the ticker through `configure_worker` regardless of the flag.
- `WORKER_MODULES` (default empty) — scope: a CSV of module names; empty = the whole registry. `Config.worker_modules_set` → `frozenset | None`; `Ticker(modules=...)` filters the registry by `entry.module`.
- `WORKER_TICK_SECONDS` (default `5`) — tick granularity (an engine knob shared by embedded and worker modes). Since the cron minimum is 1 minute, the default `5` guarantees the ticker never misses a minute boundary.
- `WORKER_MAX_CONCURRENT_RUNS` (default `10`) — the cap on concurrent tasks (an asyncio.Semaphore in `Ticker`).

## Internals

### `Ticker._loop`

```
while not stop:
    _tick_once()
    wait(tick_seconds) or exit early on stop
```

`_tick_once`:
1. **Cleanup zombies.** `crud_tasks.cleanup_zombies(threshold_seconds)` finalises `running` records with a stale `heartbeat_at` as `error("orphaned: stale heartbeat")` and returns their ids. The locks of those ids (`owner=task_run:{id}`) are released in bulk through `release_for_owners`.
2. **Registry walk.** If the ticker has a `modules` scope, other modules' entries are skipped. For each `TaskEntry` with `enabled=True` and `schedule != None` we take `last_run_at(module, code)` and check `is_due(entry.schedule, now, last)`. Due ones are spawned. Entries with `schedule=None` are always skipped by the ticker.

### Spawning and concurrency

`_spawn` creates an `asyncio.Task`, registers it in `_active` and sets a `done_callback` that removes it. Inside, `_guarded_run` limits concurrency through `asyncio.Semaphore(max_concurrent_runs)` and catches exceptions so a crashed `run_entry` does not bring down the ticker.

### `run_entry(entry)`

1. `crud_tasks.create_running(module, code)` — an UPSERT against the partial unique index `(module, code) WHERE status='running'`. Returns `task_id`, or `None` if already running. Atomic: with two simultaneous starts, the second is a no-op.
2. `CoreLock.acquire("task:{module}:{code}", ttl=entry.ttl, owner="task_run:{task_id}")`. If it is taken (e.g. a lock from a dead process lingers until its TTL) — `finalize_error("task lock busy")` and leave.
3. Starts `_heartbeat_loop(task_id, interval=30)` — updates `heartbeat_at` every 30s so another instance's ticker does not take the task for a zombie.
4. Calls `entry.handler(ctx)` under `asyncio.wait_for(timeout=entry.ttl)`.
5. `finally`:
   - `success` → `finalize_success`, `error`/`TimeoutError` → `finalize_error(text=...)` plus the traceback in `core_tasks_logs`.
   - the heartbeat task is cancelled.
   - `release_for_owners(["task_run:{task_id}"])` releases the task lock and any sub-locks with the same owner.

### Partial unique index

```sql
CREATE UNIQUE INDEX ux_core_tasks_running
  ON core_tasks (module, code) WHERE status = 'running';
```

Guarantees at the DB level that two simultaneous running tasks with the same `(module, code)` are impossible. The task lock on top of it gives TTL-bounded holding of the resource (useful in a cluster deploy: if a process is killed without a graceful shutdown, the lock releases itself on TTL).

### Heartbeat and the zombie threshold

- the handler writes `heartbeat_at` every 30s.
- `Ticker(zombie_threshold=90)` counts a task as a zombie when `heartbeat_at < now - 90s`.
- The 3× margin over the heartbeat interval covers GC pauses and brief network lags.

### Shutdown

`Ticker.stop`:
1. `_stop.set()` — `_loop` exits after the current wait/tick.
2. `await asyncio.wait_for(gather(*active), timeout=shutdown_grace_seconds)` — waits for active `run_entry` calls.
3. On timeout — `cancel()` the rest.

In `lifespan`, `scheduler.stop()` is called before `close_database`, so tasks still running can finalise through their sessions.

## Files

- `registry.py` — `TaskEntry`, `TaskRegistry`, `get_registry()`. Fields: `schedule: str | None` (cron or None), `manual_run: bool`.
- `context.py` — `TaskContext` (including the logging methods and `set_payload`).
- `runner.py` — `run_entry`, the heartbeat loop.
- `ticker.py` — `Ticker` + the `is_due(expression, now, last)` function (5-field cron). Skips entries with `schedule=None`.
- `task_base.py` — `CoreTaskBase`; attributes: `SCHEDULE: str | None`, `MANUAL_RUN: bool = False`.
- `__init__.py` — public API + `register/start/stop` + `configure_worker` (worker override). The task HTTP endpoints are in `src/core/api/system.py` (the `/api/core/tasks` router).
