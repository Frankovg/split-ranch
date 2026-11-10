"""Health, readiness and public client config."""

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from split_ranch.api.deps import SessionDep, SettingsDep

router = APIRouter(tags=["system"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
def readyz(session: SessionDep) -> JSONResponse:
    try:
        session.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return JSONResponse({"status": "ok"})


@router.get("/config")
def config(request: Request, settings: SettingsDep) -> dict[str, Any]:
    return {
        "min_app_version": settings.min_app_version,
        "features": {"sheets": False, "push": False},
    }
