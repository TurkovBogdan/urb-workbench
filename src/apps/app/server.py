"""Assembly of ``apps/app``: a headless FastAPI app (web API + serving the SPA).

The same core HTTP server serves both the API zones and the built frontend from ``web/dist``
(``core/router/spa.py``) — no nginx/Docker needed. In dev the frontend usually runs under Vite
(HMR on the sources); serving from ``web/dist`` works on the built artifact.
"""

from __future__ import annotations

from fastapi.middleware.cors import CORSMiddleware

from src.apps.app.modules import build_modules
from src.core.app_factory import create_app
from src.core.app_path import AppPath, ensure_dirs
from src.core.config import Config
from src.core.loggers import set_logger_factory
from src.core.loggers.core_logger import CoreLogger


def _bootstrap_logger(config: Config) -> None:
    """Set up the channel factory: `logs/<channel>.log` at the level from config."""
    paths = AppPath.from_root()
    ensure_dirs(paths)

    def factory(channel: str) -> CoreLogger:
        return CoreLogger(
            logs_dir=paths.logs,
            file_name=channel,
            level=config.app_log_level,
        )

    set_logger_factory(factory)


config = Config()
_bootstrap_logger(config)

app = create_app(modules=build_modules(), config=config)

# All the web wiring is gated by SERVER_ENABLED: with the server off the process is
# "worker only" (background/jobs), with no HTTP surface (zones, CORS, docs) at all.
if config.server_enabled:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=13410)
