"""FastAPI app factory.

Startup order matters: crisis-config validation (Hard Rule N8) runs before
the app accepts traffic. In Phase 0 the validator is wired but the crisis
subsystem lands in Phase 1 — the import is intentionally already here so
no later refactor can accidentally drop the gate.
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from palio.config import get_settings
from palio.routers import health

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    _validate_boot(settings)
    log.info("palio_api_started", app_env=settings.app_env, data_region=settings.data_region)
    yield


def _validate_boot(settings) -> None:
    """Boot gates. Phase 1 adds crisis-config validation here (N8)."""
    # Placeholder gate is installed in Phase 1; keep the hook point single.


def create_app() -> FastAPI:
    app = FastAPI(
        title="Palio API",
        version="0.1.0",
        description="Screens, educates, supports, refers. Never diagnoses.",
        lifespan=lifespan,
    )
    app.include_router(health.router)
    return app


app = create_app()
