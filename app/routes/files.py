"""File routes for TeleDrive (Milestone 7)."""

from __future__ import annotations

import mimetypes
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

import aiofiles
from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from starlette.background import BackgroundTask
from fastapi.responses import JSONResponse, StreamingResponse

from app import db

router = APIRouter()

MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024 * 1024
UPLOAD_TMP_DIR = Path("data/tmp/uploads")
DOWNLOAD_TMP_DIR = Path("data/tmp")


def _error_response(error_code: str, message: str, technical: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error_code": error_code,
            "message": message,
            "technical": technical,
        },
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _message_to_file_record(message, default_folder: str) -> dict:
    media = _extract_media(message)
    return {
        "tg_message_id": message.id,
        "tg_chat_id": message.chat.id,
        "remote_file_id": getattr(media, "file_id", None),
        "file_unique_id": getattr(media, "file_unique_id", None),
        "file_name": getattr(media, "file_name", None) or f"message_{message.id}",
        "mime_type": getattr(media, "mime_type", None),
        "file_size": getattr(media, "file_size", None),
        "parts": 1,
        "virtual_folder": default_folder,
        "upload_status": "uploaded",
        "uploaded_at": _utc_now(),
        "last_synced_at": _utc_now(),
        "checksum": None,
        "notes": None,
    }


def _extract_media(message):
    if getattr(message, "document", None) is not None:
        return message.document
    if getattr(message, "video", None) is not None:
        return message.video
    if getattr(message, "audio", None) is not None:
        return message.audio
    if getattr(message, "photo", None) is not None:
        return message.photo
    if getattr(message, "voice", None) is not None:
        return message.voice
    if getattr(message, "animation", None) is not None:
        return message.animation
    return None


@router.get("")
def list_files(
    request: Request,
    search: str = Query(default=""),
    folder: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
) -> JSONResponse:
    try:
        rows = db.search_files(request.app.state.db_conn, search=search, folder=folder, page=page, limit=limit)
        return JSONResponse({"items": rows, "page": page, "limit": limit})
    except Exception as exc:
        return _error_response(
            error_code="FILES_LIST_FAILED",
            message="Failed to list files.",
            technical=f"{exc}\n{traceback.format_exc()}",
            status_code=500,
        )


@router.post("/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    folder: str = Form(default="root"),
) -> JSONResponse:
    telegram_client = request.app.state.telegram_client
    queue_worker = request.app.state.queue_worker

    if not telegram_client.started:
        return _error_response(
            error_code="AUTH_REQUIRED",
            message="Telegram client is not connected. Complete login first.",
            technical="telegram_client.started is false",
            status_code=401,
        )

    try:
        UPLOAD_TMP_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = Path(file.filename or "upload.bin").name
        tmp_name = f"{uuid.uuid4().hex}_{safe_name}"
        tmp_path = UPLOAD_TMP_DIR / tmp_name

        total_bytes = 0
        async with aiofiles.open(tmp_path, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_FILE_SIZE_BYTES:
                    await out.close()
                    tmp_path.unlink(missing_ok=True)
                    return _error_response(
                        error_code="FILE_TOO_LARGE",
                        message="File exceeds maximum allowed size of 2 GB.",
                        technical=f"size_bytes={total_bytes} limit_bytes={MAX_FILE_SIZE_BYTES}",
                        status_code=400,
                    )
                await out.write(chunk)

        job_id = await queue_worker.enqueue_upload(file_path=str(tmp_path), file_name=safe_name, virtual_folder=folder)
        return JSONResponse({"job_id": job_id, "status": "queued", "folder": folder})
    except Exception as exc:
        return _error_response(
            error_code="UPLOAD_ENQUEUE_FAILED",
            message="Failed to enqueue upload.",
            technical=f"{exc}\n{traceback.format_exc()}",
            status_code=500,
        )
    finally:
        await file.close()


@router.delete("/{file_id}")
async def delete_file(file_id: int, request: Request) -> JSONResponse:
    telegram_client = request.app.state.telegram_client
    db_conn = request.app.state.db_conn

    if not telegram_client.started:
        return _error_response(
            error_code="AUTH_REQUIRED",
            message="Telegram client is not connected. Complete login first.",
            technical="telegram_client.started is false",
            status_code=401,
        )

    try:
        record = db.get_file_by_id(db_conn, file_id)
        if record is None:
            return _error_response(
                error_code="FILE_NOT_FOUND",
                message="File record not found.",
                technical=f"file_id={file_id}",
                status_code=404,
            )

        await telegram_client.delete_message(record["tg_message_id"])
        db.mark_deleted(db_conn, file_id=file_id, deleted_status="deleted_remote")
        return JSONResponse({"status": "deleted", "file_id": file_id})
    except Exception as exc:
        return _error_response(
            error_code="FILE_DELETE_FAILED",
            message="Failed to delete file from Telegram.",
            technical=f"{exc}\n{traceback.format_exc()}",
            status_code=500,
        )


@router.get("/{file_id}/download")
async def download_file(file_id: int, request: Request):
    telegram_client = request.app.state.telegram_client
    db_conn = request.app.state.db_conn

    if not telegram_client.started:
        return _error_response(
            error_code="AUTH_REQUIRED",
            message="Telegram client is not connected. Complete login first.",
            technical="telegram_client.started is false",
            status_code=401,
        )

    try:
        record = db.get_file_by_id(db_conn, file_id)
        if record is None:
            return _error_response(
                error_code="FILE_NOT_FOUND",
                message="File record not found.",
                technical=f"file_id={file_id}",
                status_code=404,
            )

        message = await telegram_client.get_message(record["tg_message_id"])
        if message is None:
            return _error_response(
                error_code="TELEGRAM_MESSAGE_NOT_FOUND",
                message="Telegram message no longer exists.",
                technical=f"tg_message_id={record['tg_message_id']}",
                status_code=404,
            )

        DOWNLOAD_TMP_DIR.mkdir(parents=True, exist_ok=True)
        tmp_path = DOWNLOAD_TMP_DIR / f"download_{uuid.uuid4().hex}"
        downloaded_path = await telegram_client.download_to_temp(message=message, target_path=str(tmp_path))

        file_name = record.get("file_name") or f"file_{file_id}"
        mime_type = record.get("mime_type") or mimetypes.guess_type(file_name)[0] or "application/octet-stream"

        file_handle = open(downloaded_path, "rb")

        def file_iterator():
            try:
                while True:
                    chunk = file_handle.read(1024 * 1024)
                    if not chunk:
                        break
                    yield chunk
            finally:
                file_handle.close()

        def cleanup() -> None:
            Path(downloaded_path).unlink(missing_ok=True)

        headers = {"Content-Disposition": f'attachment; filename="{file_name}"'}
        return StreamingResponse(
            file_iterator(),
            media_type=mime_type,
            headers=headers,
            background=BackgroundTask(cleanup),
        )
    except Exception as exc:
        return _error_response(
            error_code="FILE_DOWNLOAD_FAILED",
            message="Failed to download file from Telegram.",
            technical=f"{exc}\n{traceback.format_exc()}",
            status_code=500,
        )


@router.post("/resync")
async def resync_incremental(request: Request) -> JSONResponse:
    telegram_client = request.app.state.telegram_client
    db_conn = request.app.state.db_conn

    if not telegram_client.started:
        return _error_response(
            error_code="AUTH_REQUIRED",
            message="Telegram client is not connected. Complete login first.",
            technical="telegram_client.started is false",
            status_code=401,
        )

    try:
        last_message_id = db.get_last_indexed_message_id(db_conn)
        scanned = 0
        upserted = 0

        async for message in telegram_client.iter_saved_messages(limit=None):
            scanned += 1
            if message.id <= last_message_id:
                continue
            media = _extract_media(message)
            if media is None:
                continue

            existing = db_conn.execute(
                "SELECT virtual_folder FROM files WHERE tg_message_id = ?",
                (message.id,),
            ).fetchone()
            folder = "root" if existing is None else (existing.get("virtual_folder") or "root")

            db.upsert_file_record(db_conn, _message_to_file_record(message, folder))
            upserted += 1

        return JSONResponse(
            {
                "status": "ok",
                "mode": "incremental",
                "last_message_id": last_message_id,
                "scanned": scanned,
                "upserted": upserted,
                "last_resync_at": _utc_now(),
            }
        )
    except Exception as exc:
        return _error_response(
            error_code="RESYNC_INCREMENTAL_FAILED",
            message="Incremental resync failed.",
            technical=f"{exc}\n{traceback.format_exc()}",
            status_code=500,
        )


@router.post("/resync-full")
async def resync_full(request: Request) -> JSONResponse:
    telegram_client = request.app.state.telegram_client
    db_conn = request.app.state.db_conn

    if not telegram_client.started:
        return _error_response(
            error_code="AUTH_REQUIRED",
            message="Telegram client is not connected. Complete login first.",
            technical="telegram_client.started is false",
            status_code=401,
        )

    try:
        scanned = 0
        upserted = 0
        seen_message_ids: set[int] = set()

        async for message in telegram_client.iter_saved_messages(limit=None):
            scanned += 1
            media = _extract_media(message)
            if media is None:
                continue

            seen_message_ids.add(int(message.id))

            existing = db_conn.execute(
                "SELECT virtual_folder FROM files WHERE tg_message_id = ?",
                (message.id,),
            ).fetchone()
            folder = "root" if existing is None else (existing.get("virtual_folder") or "root")

            db.upsert_file_record(db_conn, _message_to_file_record(message, folder))
            upserted += 1

        marked_deleted = db.mark_missing_messages_deleted(db_conn, seen_message_ids)

        return JSONResponse(
            {
                "status": "ok",
                "mode": "full",
                "scanned": scanned,
                "upserted": upserted,
                "marked_deleted": marked_deleted,
                "last_resync_at": _utc_now(),
            }
        )
    except Exception as exc:
        return _error_response(
            error_code="RESYNC_FULL_FAILED",
            message="Full resync failed.",
            technical=f"{exc}\n{traceback.format_exc()}",
            status_code=500,
        )
