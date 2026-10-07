# core/loggers

Logging channels: name → `CoreLoggerProtocol` instance. One channel is one file `logs/<channel>.log`, with no hierarchy and no propagation into `logging.root`.

A slash in a channel name becomes a subfolder: `tasks/hh_vacancy_scrapper` → `logs/tasks/hh_vacancy_scrapper.log`. Subfolders are created automatically.

## Public API

```python
from src.core.loggers import get_logger, set_logger_factory, LoggerStore
```

| Name | Purpose |
|-----|------------|
| `get_logger(*channels)` | proxy for the channel(s); no arguments — `core`; ≥2 channels — tee |
| `set_logger_factory(factory)` | bootstrap: install the `(channel) -> CoreLoggerProtocol` factory |
| `LoggerStore` | channel registry; `set/get/reset` for tests |

Everything else (`CoreLogger`, `_LoggerProxy`, `CoreLoggerProtocol`, `LoggerFactory`) is an internal detail; import it straight from its module when you really need it (bootstrap, tests).

## Channels by convention

Channels are flat strings already used in the code. Don't introduce new ones without a need:

| Channel | Where it appears | File |
|-------|----------------|------|
| `core` | the `get_logger()` default | `logs/core.log` |
| `tasks` | `core/scheduler/{runner,ticker,context}.py` | `logs/tasks.log` |
| `page_scraper` | `modules/page_scraper/services/*` | `logs/page_scraper.log` |
| `hh.browser` | `modules/headhunter/browser/*` (including `scenarios.py`) | `logs/hh.browser.log` |
| `hh.scraper` | `modules/headhunter/scraper/scraper.py` | `logs/hh.scraper.log` |
| `integrated_browser` | `modules/integrated_browser/*` | `logs/integrated_browser.log` |

## Usage

### One channel

```python
# src/modules/page_scraper/services/gateway.py
from src.core.loggers import get_logger

_LOG = get_logger("page_scraper")  # → logs/page_scraper.log

def set_server(...) -> None:
    _LOG.info("server set: %s", endpoint)
```

### The default `core` channel

```python
_LOG = get_logger()
_LOG.info("startup")               # writes to logs/core.log
```

### Subchannel (subfolder)

A slash in the name → the file lives in a nested directory. Handy when one "domain" (say, `tasks`) has many child streams and you want to group them physically:

```python
_LOG = get_logger("tasks/hh_vacancy_scrapper")  # → logs/tasks/hh_vacancy_scrapper.log
```

This is just file naming; for `LoggerStore` the channel stays the flat string `"tasks/hh_vacancy_scrapper"` — separate from `"tasks"`. To write to **both** the shared channel **and** the subchannel, use a tee.

### Several channels at once (fan-out)

```python
_LOG = get_logger("hh.browser", "tasks")
_LOG.info("vacancy %s scraped in %.2fs", vacancy_id, elapsed)
# → the line lands in logs/hh.browser.log AND in logs/tasks.log
```

A tee fits subchannels well too — the detailed log goes to its own file, the shared stream to `tasks`:

```python
_LOG = get_logger("tasks", "tasks/hh_vacancy_scrapper")
# → logs/tasks.log + logs/tasks/hh_vacancy_scrapper.log
```

`set_level` on a tee applies to all its channels at once.

## Layout

| File | Role |
|------|------|
| `logger_protocol.py` | `CoreLoggerProtocol` — the minimal contract |
| `logger_store.py` | `LoggerStore` ("channel → instance" cache) + `set_logger_factory` |
| `core_logger.py` | `CoreLogger` — writes to `logs/<channel>.log`, no stdout |
| `logger_proxy.py` | `_LoggerProxy` / `_TeeProxy`, `get_logger` |
| `__init__.py` | public facade: `get_logger`, `set_logger_factory`, `LoggerStore` |

## The proxy: why it exists

`get_logger(...)` returns a **proxy**, not an instance. Every log call is resolved through `LoggerStore.get(channel)`:

```python
# In a module, at import time — the bootstrap has not run yet.
_LOG = get_logger("tasks")   # this is _LoggerProxy("tasks")

# Later apps/app/server.py runs set_logger_factory(...).
# The next call already resolves through the new factory:
_LOG.info("task started")    # writes to logs/tasks.log at the right level
```

If `get_logger` handed out the instance itself, modules with a module-level `_LOG = get_logger(...)` would capture the default logger created before the bootstrap and ignore the configuration. `_TeeProxy` works the same way: on every call it resolves each channel through the store.

## Bootstrap

`src/apps/app/server.py`:

```python
from src.core.app_path import AppPath, ensure_dirs
from src.core.loggers import set_logger_factory
from src.core.loggers.core_logger import CoreLogger

def _bootstrap_logger(settings: Settings) -> None:
    paths = AppPath.from_root()
    ensure_dirs(paths)

    def factory(channel: str) -> CoreLogger:
        return CoreLogger(
            logs_dir=paths.logs,
            file_name=channel,
            level=settings.log_level,
        )

    set_logger_factory(factory)
```

`set_logger_factory` drops the channels already cached — early imports made before the bootstrap don't get stuck with the old configuration.

## Tests

`tests/core/test_loggers.py` resets the store with an autouse fixture:

```python
@pytest.fixture(autouse=True)
def _reset_store():
    LoggerStore.reset()
    yield
    LoggerStore.reset()
```

Overriding a channel with a specific instance:

```python
custom = CoreLogger(logs_dir=tmp_path, file_name="custom")
LoggerStore.set(custom, "tasks")   # pins the instance to the "tasks" channel
LoggerStore.set(None, "tasks")     # removes the override
```

Replacing the whole factory:

```python
set_logger_factory(lambda ch: CoreLogger(
    logs_dir=tmp_path, file_name=ch, level=logging.DEBUG
))
get_logger("hh.browser", "tasks").info("fanout")

for ch in ("hh.browser", "tasks"):
    for h in logging.getLogger(f"core.{ch}").handlers:
        h.flush()
    assert "fanout" in (tmp_path / f"{ch}.log").read_text()
```
