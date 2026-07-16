"""FastAPI app factory.

Startup order matters: crisis-config validation (Hard Rule N8) runs in the
lifespan hook before the app accepts traffic. Production (or unset APP_ENV)
with placeholder crisis resources does not boot — no exceptions.
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from palio.config import Settings, get_settings
from palio.routers import crisis as crisis_router
from palio.routers import health
from palio.safety import crisis_config

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.crisis_verified = _validate_boot(settings)
    log.info(
        "palio_api_started",
        app_env=settings.app_env,
        data_region=settings.data_region,
        crisis_resources_verified=app.state.crisis_verified,
    )
    yield


def _validate_boot(settings: Settings) -> bool:
    """Boot gates. Raises CrisisConfigError (=> no boot) on N8 violation."""
    verified = crisis_config.validate_at_boot(settings)
    if not verified:
        log.warning(
            "crisis_config_unverified_dev_mode",
            note="running with UNVERIFIED crisis resources under the dev escape hatch; "
            "production boot would refuse (Hard Rule N8)",
        )
    return verified


def create_app() -> FastAPI:
    app = FastAPI(
        title="Palio API",
        version="0.1.0",
        description="Screens, educates, supports, refers. Never diagnoses.",
        lifespan=lifespan,
    )
    app.include_router(health.router)
    app.include_router(crisis_router.router)
    return app


app = create_app()
