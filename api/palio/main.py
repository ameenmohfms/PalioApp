"""FastAPI app factory.

Startup order matters: crisis-config validation (Hard Rule N8) runs in the
lifespan hook before the app accepts traffic. Production (or unset APP_ENV)
with placeholder crisis resources does not boot — no exceptions.
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from palio.config import Settings, get_settings
from palio.routers import auth as auth_router
from palio.routers import chat as chat_router
from palio.routers import crisis as crisis_router
from palio.routers import health
from palio.routers import screeners as screeners_router
from palio.safety import crisis_config

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.crisis_verified = _validate_boot(settings)
    _sync_instruments()
    log.info(
        "palio_api_started",
        app_env=settings.app_env,
        data_region=settings.data_region,
        crisis_resources_verified=app.state.crisis_verified,
    )
    yield


def _validate_boot(settings: Settings) -> bool:
    """Boot gates. Raises (=> no boot) on N8 violation or insecure prod auth."""
    if settings.is_production and settings.jwt_secret == "dev-only-not-a-secret":
        raise RuntimeError("REFUSING TO BOOT: JWT_SECRET must be set in production")
    verified = crisis_config.validate_at_boot(settings)
    if not verified:
        log.warning(
            "crisis_config_unverified_dev_mode",
            note="running with UNVERIFIED crisis resources under the dev escape hatch; "
            "production boot would refuse (Hard Rule N8)",
        )
    return verified


def _sync_instruments() -> None:
    """Upsert versioned instrument files into the DB (Hard Rule A3)."""
    from palio.assessments import loader
    from palio.db.base import db_session

    try:
        with db_session() as session:
            added = loader.sync_to_db(session)
        if added:
            log.info("instruments_synced", added=added)
    except Exception as exc:  # noqa: BLE001 — DB may lag behind at boot; endpoints still guard
        log.warning("instrument_sync_failed", error=str(exc))


def create_app() -> FastAPI:
    app = FastAPI(
        title="Palio API",
        version="0.1.0",
        description="Screens, educates, supports, refers. Never diagnoses.",
        lifespan=lifespan,
    )
    app.include_router(health.router)
    app.include_router(crisis_router.router)
    app.include_router(auth_router.router)
    app.include_router(chat_router.router)
    app.include_router(screeners_router.router)
    return app


app = create_app()
