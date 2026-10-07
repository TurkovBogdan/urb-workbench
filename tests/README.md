# Test system
> Rules for writing tests and the commands to run them — all here.

We use `Pytest` + `pytest-xdist`, and test type markers. 

## Test database setup
> No setup is required: tests run on **in-memory `SQLite`** (`DB_PROVIDER=sqlite`, `DB_PATH=:memory:`). An external `PostgreSQL` server and a database pool are no longer needed.

`conftest.py` overrides `DB_*` before any import from `src`, so any `Config()` in a test gets a clean in-memory database. Each test's schema is built from the ORM models (`create_all` in the lifespan or in a local `db` fixture). Isolation of a parallel run is free: each xdist worker is a separate process with its own `:memory:` database, so hitting the dev/prod DB is impossible in principle.

**Heavy Alembic migration tests — Postgres only.** The migrations are written in `postgresql.*` types (JSONB/TIMESTAMP) and do not apply on SQLite, so by default such tests are skipped. To run them against a real database, set the DSN of an administrative connection (a role with the `CREATEDB` privilege):
```dotenv
TEST_PG_DSN=postgresql://user:pass@host:port/postgres
```
The DSN database is only where `CREATE DATABASE` runs: for each heavy test the fixture creates its own disposable database `urb_test_<hex>` and drops it afterwards (`DROP DATABASE … WITH (FORCE)`), so `--heavy` is equally green under `-n auto` and `-n0`. The other tests of the same run stay on in-memory SQLite. Bring up a local server for this any way you like — the repository has no stand for it.

## Test layout
Tests must sit in folders mirroring the main `src` structure:
- build and application tests in `apps`
- module tests in `modules`, split into per-module folders
- core tests in `core`

- Example:
```
tests/
├─ core/                 # the platform core
├─ apps/                 # build and applications
├─ modules/
│  ├─ intercom/          # mirrors the module's layers
│  │  ├─ crud/
│  │  ├─ models/
│  │  ├─ services/
│  │  ├─ importers/
│  │  └─ live/           # tests against real services
│  └─ mail_sync/
└─ conftest.py           # test configuration
```

## Test type markers
Every test must carry a test type marker:
~~~python
# Mark that the test uses db
@pytest.mark.db
async def test_returns_empty_list_when_no_tasks_registered(db):
    r = await _get_tasks(_client_app())
    assert r.json() == []
~~~

| Marker  | Meaning |
|---------|---|
| `pure`  | no DB and no network; the only ones that don't touch the schema |
| `db`    | needs a DB — in-memory SQLite, schema from the ORM models |
| `heavy` | real Alembic migrations — Postgres only (`TEST_PG_DSN`), otherwise skipped |
| `live`  | real external services (credentials + network) |

> Transactional behaviour is not tested on the in-memory database: there is one driver connection for all sessions, and therefore one transactional state (which is why the application doesn't intercept transaction start for `:memory:`). Everything about `BEGIN IMMEDIATE`, pragma switching and migration transactions runs on a file database in `tmp_path`; see the examples in `tests/core/test_sqlite_pragmas.py`. The write-intent guard works everywhere: a mutating statement inside `session_scope()` fails the test in any tier.

> By default `pure` + `db` run — the working set. `heavy` and `live` are triggered by the separate `--heavy` / `--live` switches when really needed. Everything at once — `--all`.

## Running tests
> Run every command from the project root

### Area flags 
Tests are split into core and module areas, technically into folders. For convenience there are two options:
```bash
# Core and apps tests
pytest --core
# Tests of one module
pytest --module=core_users
# A set of modules
pytest --module=core_users,core_storage
```

### Marker flags
By default tests marked `pure` and `db` run, without the `heavy` and `live` tests
Running those is controlled by separate flags:
```bash
# default — pure + db
pytest --core
# pure only
pytest --core --pure
# db only
pytest --core --db
# heavy only
pytest --core --heavy
# live only
pytest --core --live
# All tests 
pytest --core --all
# Lost tests without a type marker
pytest --unmarked --collect-only
```

### Worker flags
> Parallelism is unrestricted — each xdist worker has its own in-memory database (a separate process). The default is `-n auto` (by core count).

```bash
# Default — parallel by core count
pytest --core
# Fix the number of workers
pytest --core -n 4
# Single process (needed for --pdb)
pytest --core -n0
```
> The `--dbs` option is deprecated (there is no DB pool any more) and ignored — kept as a no-op so that old commands don't fail.
