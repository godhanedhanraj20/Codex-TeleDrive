"""TeleDrive application entrypoint (Milestone 9 dashboard wiring)."""

from __future__ import annotations

import os
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.db import get_connection, initialize_database
from app.queue_worker import QueueWorker
from app.routes.auth import router as auth_router
from app.routes.files import router as files_router
from app.routes.queue import router as queue_router
from app.telegram_client import TelegramClient

APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
UPLOAD_CONCURRENCY = int(os.getenv("UPLOAD_CONCURRENCY", "1"))
UPLOAD_DELAY = int(os.getenv("UPLOAD_DELAY", "2"))


def _ensure_data_directories() -> None:
    Path("data").mkdir(parents=True, exist_ok=True)
    Path("data/tmp").mkdir(parents=True, exist_ok=True)
    Path("data/logs").mkdir(parents=True, exist_ok=True)


def _configure_logging() -> None:
    log_path = Path("data/logs/teledrive.log")
    handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=3)
    formatter = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(isinstance(existing, RotatingFileHandler) for existing in root.handlers):
        root.addHandler(handler)


def _cleanup_stale_temp_files(max_age_seconds: int = 24 * 60 * 60) -> int:
    now = Path("data/tmp")
    deleted = 0
    if not now.exists():
        return deleted

    current_ts = time.time()
    for path in now.rglob("*"):
        if not path.is_file():
            continue
        try:
            age = current_ts - path.stat().st_mtime
            if age > max_age_seconds:
                path.unlink(missing_ok=True)
                deleted += 1
        except Exception:
            logging.getLogger("teledrive.main").exception("Failed stale temp cleanup for %s", path)
    return deleted


@asynccontextmanager
async def lifespan(app: FastAPI):
    _ensure_data_directories()
    _configure_logging()
    cleaned = _cleanup_stale_temp_files()
    logging.getLogger("teledrive.main").info("startup temp cleanup complete deleted=%s", cleaned)

    db_conn = get_connection()
    initialize_database(db_conn)
    logging.getLogger("teledrive.main").info("database initialized")

    telegram_client = TelegramClient()

    queue_worker = QueueWorker(
        db_conn=db_conn,
        telegram_client=telegram_client,
        upload_delay_seconds=UPLOAD_DELAY,
    )
    await queue_worker.start()

    app.state.db_conn = db_conn
    app.state.telegram_client = telegram_client
    app.state.queue_worker = queue_worker

    try:
        yield
    finally:
        await queue_worker.stop()
        await telegram_client.stop()
        db_conn.close()
        logging.getLogger("teledrive.main").info("shutdown complete")


app = FastAPI(title="TeleDrive", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(files_router, prefix="/api/files", tags=["files"])
app.include_router(queue_router, prefix="/api/queue", tags=["queue"])


@app.get("/")
def dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health")
def health() -> JSONResponse:
    """Basic health route for lifecycle verification."""
    return JSONResponse(
        {
            "status": "ok",
            "host": APP_HOST,
            "port": APP_PORT,
            "upload_concurrency": UPLOAD_CONCURRENCY,
            "upload_delay": UPLOAD_DELAY,
        }
    )
