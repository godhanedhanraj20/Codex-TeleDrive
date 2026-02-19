"""Single-worker upload queue for TeleDrive (Milestone 5)."""

from __future__ import annotations

import asyncio
import hashlib
import traceback
from datetime import datetime, timezone
from pathlib import Path

from app import db
from app.telegram_client import TelegramClient


class QueueWorker:
    """Single-concurrency upload queue with manual retry semantics."""

    def __init__(
        self,
        db_conn,
        telegram_client: TelegramClient,
        upload_delay_seconds: int = 2,
    ) -> None:
        self.db_conn = db_conn
        self.telegram_client = telegram_client
        self.upload_delay_seconds = upload_delay_seconds
        self.running = False
        self._queue: asyncio.Queue[int] = asyncio.Queue()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self.running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def enqueue_upload(self, file_path: str, file_name: str, virtual_folder: str) -> int:
        checksum = self._compute_checksum(file_path)
        duplicate = db.find_file_by_checksum(self.db_conn, checksum)
        if duplicate is not None:
            raise ValueError(f"Duplicate file checksum found. existing_file_id={duplicate['id']}")

        now = _utc_now()
        job_id = db.create_job(
            self.db_conn,
            checksum=checksum,
            file_name=file_name,
            source_path=file_path,
            virtual_folder=virtual_folder,
            status="queued",
            error=None,
            created_at=now,
            updated_at=now,
        )
        await self._queue.put(job_id)
        return job_id

    async def retry_failed_job(self, job_id: int) -> None:
        job = db.get_job_by_id(self.db_conn, job_id)
        if job is None:
            raise ValueError(f"Job not found. job_id={job_id}")
        if job["status"] != "failed":
            raise ValueError(f"Only failed jobs can be retried. job_id={job_id} status={job['status']}")

        db.update_job_status(self.db_conn, job_id=job_id, status="queued", error=job["error"], updated_at=_utc_now())
        await self._queue.put(job_id)

    async def _run(self) -> None:
        while self.running:
            job_id = await self._queue.get()
            try:
                await self._process_job(job_id)
            finally:
                self._queue.task_done()

    async def _process_job(self, job_id: int) -> None:
        job = db.get_job_by_id(self.db_conn, job_id)
        if job is None:
            return

        try:
            file_path = job.get("source_path")
            if not file_path:
                raise RuntimeError("Missing source_path for upload job")
            if not Path(file_path).exists():
                raise FileNotFoundError(f"Upload source path does not exist: {file_path}")
            if not self.telegram_client.started:
                raise RuntimeError("Telegram client is not started. Complete auth flow before upload.")

            db.update_job_status(self.db_conn, job_id=job_id, status="uploading", error=job["error"], updated_at=_utc_now())
            message = await self.telegram_client.upload_file(path=file_path)

            db.upsert_file_record(
                self.db_conn,
                {
                    "tg_message_id": message.id,
                    "tg_chat_id": message.chat.id,
                    "remote_file_id": getattr(getattr(message, "document", None), "file_id", None),
                    "file_unique_id": getattr(getattr(message, "document", None), "file_unique_id", None),
                    "file_name": getattr(getattr(message, "document", None), "file_name", None),
                    "mime_type": getattr(getattr(message, "document", None), "mime_type", None),
                    "file_size": getattr(getattr(message, "document", None), "file_size", None),
                    "parts": 1,
                    "virtual_folder": job.get("virtual_folder") or "root",
                    "upload_status": "uploaded",
                    "uploaded_at": _utc_now(),
                    "last_synced_at": _utc_now(),
                    "checksum": job.get("checksum"),
                    "notes": None,
                },
            )
            db.update_job_status(self.db_conn, job_id=job_id, status="done", error=None, updated_at=_utc_now())
        except Exception as exc:
            flood_wait_seconds = self.telegram_client.extract_flood_wait_seconds(exc)
            flood_info = f" flood_wait_seconds={flood_wait_seconds}" if flood_wait_seconds is not None else ""
            technical = f"{exc}{flood_info}\n{traceback.format_exc()}"
            db.update_job_status(self.db_conn, job_id=job_id, status="failed", error=technical, updated_at=_utc_now())
        finally:
            try:
                if job.get("source_path"):
                    Path(job["source_path"]).unlink(missing_ok=True)
            except Exception:
                pass
            await asyncio.sleep(self.upload_delay_seconds)

    @staticmethod
    def _compute_checksum(file_path: str) -> str:
        hasher = hashlib.sha256()
        with open(file_path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
        return hasher.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
