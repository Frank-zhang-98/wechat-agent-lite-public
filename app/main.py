from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from app.api import router as api_router
from app.core.security import allow_insecure_secret_storage, has_external_encryption_key
from app.core.version import get_console_page_title, get_console_version
from app.db import Base, engine, ensure_runtime_indexes, get_session
from app.models import ConfigEntry
from app.services.model_pricing_service import warm_pricing_catalog
from app.services.scheduler_service import SchedulerService
from app.services.settings_service import SettingsService
from app import state

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
scheduler_service = SchedulerService()
state.scheduler = scheduler_service
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    app_version = get_console_version()
    logger.info("starting wechat-agent-lite %s", app_version)
    Base.metadata.create_all(bind=engine)
    ensure_runtime_indexes()
    with get_session() as session:
        SettingsService(session).ensure_defaults()
        stored_secret_count = session.execute(
            select(func.count()).select_from(ConfigEntry).where(ConfigEntry.is_secret.is_(True), ConfigEntry.value != "")
        ).scalar_one()
        if int(stored_secret_count or 0) > 0 and not has_external_encryption_key() and not allow_insecure_secret_storage():
            logger.warning(
                "stored secrets detected without WAL_ENCRYPTION_KEY; "
                "falling back to legacy compatibility key for startup. "
                "Set WAL_ENCRYPTION_KEY explicitly to keep future deployments stable."
            )
    try:
        warm_pricing_catalog()
    except Exception:
        pass
    scheduler_service.start()
    try:
        yield
    finally:
        scheduler_service.stop()


app = FastAPI(title="wechat-agent-lite", lifespan=lifespan)
app.include_router(api_router)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    app_version = get_console_version()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "app_version": app_version,
            "page_title": get_console_page_title(version=app_version),
        },
    )
