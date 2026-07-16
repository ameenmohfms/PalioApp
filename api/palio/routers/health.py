from fastapi import APIRouter
from sqlalchemy import text

from palio.db.base import get_engine

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict:
    with get_engine().connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}
