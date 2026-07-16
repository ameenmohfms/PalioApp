"""Crisis resources endpoint.

The app fetches and caches this so the crisis screen works offline (§10.8).
Deliberately unauthenticated: crisis resources must never be behind a login.
"""

from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from palio.safety import crisis_config

router = APIRouter(prefix="/crisis", tags=["crisis"])


@router.get("/resources/{country}")
def resources(country: str) -> dict:
    payload = crisis_config.load(country)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"no crisis resources for {country!r}")
    return asdict(payload)
