"""Health, readiness and public client config."""

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from split_ranch.api.deps import SessionDep, SettingsDep

router = APIRouter(tags=["system"])

PAYMENT_APPS_ANDROID = [
    {"id": "caixabank", "name": "CaixaBank", "package": "es.lacaixa.mobile.android.newwapicon"},
    {"id": "bbva", "name": "BBVA", "package": "com.bbva.bbvacontigo"},
    {"id": "santander", "name": "Santander", "package": "es.bancosantander.apps"},
    {
        "id": "sabadell",
        "name": "Sabadell",
        "package": "net.inverline.bancosabadell.officelocator.android",
    },
    {"id": "ing", "name": "ING", "package": "www.ingdirect.nativeframe"},
    {"id": "imagin", "name": "imagin", "package": "com.imaginbank.app"},
    {"id": "openbank", "name": "Openbank", "package": "es.openbank.mobile"},
]


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
        "payment_apps": {"android": PAYMENT_APPS_ANDROID},
        "features": {"quick_share_links": True, "sheets": False, "push": False},
    }
