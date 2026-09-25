"""Read-only LAN HTTP API (Step 4) — served on the 1080 while awake.

GET  /feeds/{role}   per-role bounded feeds
GET  /quality        data quality report
GET  /failures       structured failure reports
GET  /history        conversation history (rolling window)
POST /recommendation the ONLY write: apply a team recommendation to the
                      paper portfolio and trigger delivery

Bind: API_HOST/API_PORT (default 0.0.0.0:8400, LAN).

Usage:
  python -m api.server
"""
from __future__ import annotations

import logging
import sys

from fastapi import FastAPI

from common import config
from api import routes

log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title="Portfolio Manager read-only API", version="1.0")
    app.include_router(routes.feeds.router)
    app.include_router(routes.quality.router)
    app.include_router(routes.failures.router)
    app.include_router(routes.history.router)
    app.include_router(routes.metrics.router)
    app.include_router(routes.recommendation.router)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    return app


def main() -> int:
    config.load_env()
    import uvicorn

    host = config.get("API_HOST", "0.0.0.0") or "0.0.0.0"
    port = config.get_int("API_PORT", 8400)
    log.info("starting read-only API on %s:%d", host, port)
    uvicorn.run(create_app(), host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    sys.exit(main())
