"""Pyrogram user-client wrapper for TeleDrive (Milestone 2)."""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

from pyrogram import Client
from pyrogram.errors import FloodWait
from pyrogram.types import Message

LOGGER = logging.getLogger("teledrive.telegram_client")

class TelegramClient:
    """Thin Pyrogram wrapper for single-account Saved Messages operations."""

    def __init__(
        self,
        session_name: str = "teledrive",
        workdir: str | Path = "data",
        api_id: int | None = None,
        api_hash: str | None = None,
    ) -> None:
        self._workdir = Path(workdir)
        self._workdir.mkdir(parents=True, exist_ok=True)
        self._session_name = session_name
        self._api_id = api_id
        self._api_hash = api_hash
        self._client: Client | None = None
        self._started = False

    @property
    def started(self) -> bool:
        return self._started

    def _build_client(self) -> Client:
        resolved_api_id = self._api_id if self._api_id is not None else int(os.environ["TG_API_ID"])
        resolved_api_hash = self._api_hash if self._api_hash is not None else os.environ["TG_API_HASH"]
        return Client(
            self._session_name,
            api_id=resolved_api_id,
            api_hash=resolved_api_hash,
            workdir=str(self._workdir),
        )

    def _require_client(self) -> Client:
        if self._client is None:
            raise RuntimeError("Telegram client not initialized. Call start() first.")
        return self._client

    async def start(self) -> None:
        if self._started:
            return

        if self._client is None:
            self._client = self._build_client()

        # Use connect() (not start()) because start() triggers interactive terminal
        # prompts when no authorization exists, which breaks API-driven auth flows.
        if getattr(self._client, "is_connected", False):
            self._started = True
            return

        try:
            await self._client.connect()
            self._started = True
            return
        except ConnectionError as exc:
            if "already connected" not in str(exc).lower():
                raise
            self._started = True
            return
        except sqlite3.OperationalError as exc:
            if "no such table: version" not in str(exc):
                raise

            # Pyrogram stores its own SQLite schema in data/teledrive.session;
            # if this file is partially initialized/corrupted, startup can fail with
            # a missing internal "version" table error.
            LOGGER.warning(
                "Detected corrupted Pyrogram session schema; removing session files and retrying once",
                extra={
                    "error": str(exc),
                    "session_file": "data/teledrive.session",
                },
            )

            # Removing only the Pyrogram session files is safe: this does not touch
            # TeleDrive's main metadata DB (data/teledrive.db).
            Path("data/teledrive.session").unlink(missing_ok=True)
            Path("data/teledrive.session-journal").unlink(missing_ok=True)

            # Retry exactly once to avoid masking persistent/unrelated issues.
            self._client = self._build_client()
            await self._client.connect()
            self._started = True

    async def stop(self) -> None:
        if self._started:
            client = self._require_client()
            if getattr(client, "is_connected", False):
                await client.disconnect()
            self._started = False

    async def send_code(self, phone: str) -> dict[str, Any]:
        sent = await self._require_client().send_code(phone)
        return {
            "phone_code_hash": sent.phone_code_hash,
            "type": str(sent.type),
            "next_type": str(sent.next_type) if sent.next_type else None,
            "timeout": sent.timeout,
        }

    async def sign_in(self, phone: str, phone_code_hash: str, code: str) -> dict[str, Any]:
        result = await self._require_client().sign_in(phone_number=phone, phone_code_hash=phone_code_hash, phone_code=code)
        return self._auth_result_to_dict(result)

    async def check_password(self, password: str) -> dict[str, Any]:
        result = await self._require_client().check_password(password=password)
        return self._auth_result_to_dict(result)

    async def get_status(self) -> dict[str, Any]:
        if not self._started:
            return {"connected": False, "user": None}

        try:
            me = await self._require_client().get_me()
            return {
                "connected": True,
                "user": {
                    "id": me.id,
                    "name": " ".join(part for part in [me.first_name, me.last_name] if part).strip() or me.username,
                    "username": me.username,
                    "phone_number": me.phone_number,
                },
            }
        except Exception as exc:
            if "AUTH_KEY_UNREGISTERED" not in str(exc):
                raise
            LOGGER.warning(
                "Detected unregistered Telegram auth key; resetting Pyrogram session files",
                extra={"session_file": "data/teledrive.session"},
            )
            if self._client is not None and getattr(self._client, "is_connected", False):
                await self._client.disconnect()
            self._started = False
            self._client = None
            Path("data/teledrive.session").unlink(missing_ok=True)
            Path("data/teledrive.session-journal").unlink(missing_ok=True)
            return {"connected": False, "user": None}

    async def upload_file(self, path: str, caption: str | None = None) -> Message:
        return await self._require_client().send_document("me", path, caption=caption)

    async def download_to_temp(self, message: Message, target_path: str) -> str:
        downloaded = await self._require_client().download_media(message, file_name=target_path)
        if downloaded is None:
            raise RuntimeError("download_media returned None")
        return downloaded

    async def iter_saved_messages(self, limit: int | None = None):
        async for message in self._require_client().get_chat_history("me", limit=limit):
            yield message

    async def get_message(self, message_id: int) -> Message | None:
        return await self._require_client().get_messages("me", message_ids=message_id)

    async def delete_message(self, message_id: int) -> int:
        return await self._require_client().delete_messages("me", message_ids=message_id)

    @staticmethod
    def extract_flood_wait_seconds(exc: Exception) -> int | None:
        if isinstance(exc, FloodWait):
            return int(exc.value)
        return None

    @staticmethod
    def _auth_result_to_dict(result: Any) -> dict[str, Any]:
        if result is None:
            return {"status": "ok", "user": None}

        return {
            "status": "ok",
            "user": {
                "id": getattr(result, "id", None),
                "name": " ".join(
                    part
                    for part in [getattr(result, "first_name", None), getattr(result, "last_name", None)]
                    if part
                ).strip()
                or getattr(result, "username", None),
                "username": getattr(result, "username", None),
                "phone_number": getattr(result, "phone_number", None),
            },
        }
