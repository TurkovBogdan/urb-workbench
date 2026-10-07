# core/database

Async SQLAlchemy 2.0 + asyncpg + Alembic.

## Lifecycle

The engine and session factory live at module level in `runtime.py` — one process, one engine. `init_database(settings)` creates them, `close_database()` resets them. They are created inside the factory's lifespan (`src/core/app_factory.py`).

```python
# Inside the create_app() lifespan:
engine = await init_database(settings)
await AlembicRunner(modules=modules).upgrade_head(engine)
# ... yield ...
await close_database()
```

The current engine is `get_engine()` (or `None` if not yet initialized).

## Session access

The session is owned by **CRUD**, not by the caller. Each CRUD function opens `session_scope()` itself and commits on exit; HTTP handlers, services and jobs call CRUD directly, with no `session` argument.

`session_scope()` directly — only inside CRUD and in the rare places that need an ad-hoc query outside the CRUD layer:

```python
from src.core.database import session_scope

async with session_scope() as session:
    await session.execute(...)
    # commit on success, rollback on exception
```

## Adding a migration for a module

Each module in `src/modules/<name>/` keeps its own models and its own revisions folder. The core knows nothing about a module's models — they are registered in `Base.metadata` by importing `models` in the module's `__init__.py`.

**1. Model.** `src/modules/<name>/models.py`:

```python
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base

class Vacancy(Base):
    __tablename__ = "vacancies"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
```

**2. Registration in SPEC.** `src/modules/<name>/__init__.py`:

```python
from pathlib import Path
from src.core.module_spec import ModuleSpec
from src.modules.<name> import models  # noqa: F401 — registers in Base.metadata
from src.modules.<name>.api import router

_NAME = "<short-name>"
_HERE = Path(__file__).resolve().parent

def _register(app, settings):
    app.include_router(router, prefix=f"/api/{_NAME}", tags=[_NAME])

SPEC = ModuleSpec(
    name=_NAME,
    register=_register,
    migrations_dir=_HERE / "migrations" / "versions",
    settings_cls=...,
)
```

**3. Wiring into the build.** `src/apps/app/server.py`:

```python
from src.modules import <name>
app = create_app(modules=[headhunter.SPEC, <name>.SPEC], settings=settings)
```

**4. Creating a revision.** For now by hand, through the alembic CLI with an explicit `script_location` and `version_locations`; the wrapper script `scripts/db_revision.py` is not written yet (TODO).

**5. Applying.** With an explicit command — `uv run python src/app.py migrate upgrade` (`AlembicRunner(modules=modules).upgrade_head(engine)` assembles `version_locations` from every module's `m.migrations_dir`). Starting the app does NOT apply migrations.

### The behind-chain gate (instead of an auto-migrate flag)

Applying migrations is always explicit and always done from outside the app: for a user it is the installation update, for a developer `src/app.py migrate upgrade`. The switch that enabled auto-apply on startup is gone.

**Why:** in development the backend runs with `--hot-reload`, and saving a revision file restarted the process, which carried a **half-written** migration into the live database (real incidents: a reload applied `ci01_init` with `depends_on` pointing at someone else's head and jammed Alembic; on 2026-09-11 the same happened again on the dev database).

**What startup does instead of applying** (`app_factory.lifespan` → `_apply_chain_or_degrade`): it takes `AlembicRunner.status`. An empty database (not a single applied head) is a fresh install: the chain is applied silently. A database that has a schema but is behind — the app comes up in stub mode (`src/core/router/degraded.py`): every request → 503 (HTML to a browser, JSON to the `/api`, `/mcp`, `/storage` zones), `/internal/health` answers 200 with `{"status": "degraded", "pending": [...]}`, the scheduler does not start. To check ahead of time — `src/app.py migrate check` (dry-run: lists pending, does not touch the database, exit 1 on drift).

## Files

- `runtime.py` — `Base`, `init_database`, `close_database`, `get_engine`, `session_scope`.
- `migrations.py` — `AlembicRunner(modules)`: the Alembic programmatic API, `path_separator=os`, `version_locations` joined from the ModuleSpecs.
- `alembic/env.py` — a standard env, imports `Base.metadata`. Called from inside `AlembicRunner`.
- `alembic/script.py.mako` — the revision template.

## TODO

- `scripts/db_revision.py` — a wrapper over `alembic revision --autogenerate` that knows the path to the given module's `versions/`.
