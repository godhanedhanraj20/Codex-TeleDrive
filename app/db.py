"""SQLite database helpers for TeleDrive (Milestone 1)."""

from __future__ import annotations

import sqlite3
import logging
from pathlib import Path
from typing import Any

DB_PATH = Path("data/teledrive.db")
LOGGER = logging.getLogger("teledrive.db")


def _dict_factory(cursor: sqlite3.Cursor, row: tuple[Any, ...]) -> dict[str, Any]:
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def get_connection(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = _dict_factory
    return conn


def apply_pragmas(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")


def initialize_database(conn: sqlite3.Connection) -> None:
    apply_pragmas(conn)

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS files (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          tg_message_id INTEGER NOT NULL UNIQUE,
          tg_chat_id INTEGER NOT NULL,
          remote_file_id TEXT,
          file_unique_id TEXT,
          file_name TEXT,
          mime_type TEXT,
          file_size INTEGER,
          parts INTEGER DEFAULT 1,
          virtual_folder TEXT DEFAULT 'root',
          upload_status TEXT NOT NULL DEFAULT 'uploaded',
          uploaded_at TEXT NOT NULL,
          last_synced_at TEXT,
          checksum TEXT,
          notes TEXT
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_files_name ON files(file_name);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_files_uploaded_at ON files(uploaded_at);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_files_unique ON files(file_unique_id);")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          checksum TEXT,
          file_name TEXT,
          source_path TEXT,
          virtual_folder TEXT,
          status TEXT,
          error TEXT,
          created_at TEXT,
          updated_at TEXT
        );
        """
    )

    _ensure_jobs_source_path_column(conn)
    _ensure_jobs_virtual_folder_column(conn)
    conn.commit()
    LOGGER.info("initialize_database complete")


def _ensure_jobs_source_path_column(conn: sqlite3.Connection) -> None:
    columns = conn.execute("PRAGMA table_info(jobs)").fetchall()
    existing = {column["name"] for column in columns}
    if "source_path" not in existing:
        conn.execute("ALTER TABLE jobs ADD COLUMN source_path TEXT")



def _ensure_jobs_virtual_folder_column(conn: sqlite3.Connection) -> None:
    columns = conn.execute("PRAGMA table_info(jobs)").fetchall()
    existing = {column["name"] for column in columns}
    if "virtual_folder" not in existing:
        conn.execute("ALTER TABLE jobs ADD COLUMN virtual_folder TEXT DEFAULT 'root'")

def upsert_file_record(conn: sqlite3.Connection, record: dict[str, Any]) -> int:
    conn.execute(
        """
        INSERT INTO files (
          tg_message_id,
          tg_chat_id,
          remote_file_id,
          file_unique_id,
          file_name,
          mime_type,
          file_size,
          parts,
          virtual_folder,
          upload_status,
          uploaded_at,
          last_synced_at,
          checksum,
          notes
        ) VALUES (
          :tg_message_id,
          :tg_chat_id,
          :remote_file_id,
          :file_unique_id,
          :file_name,
          :mime_type,
          :file_size,
          :parts,
          :virtual_folder,
          :upload_status,
          :uploaded_at,
          :last_synced_at,
          :checksum,
          :notes
        )
        ON CONFLICT(tg_message_id) DO UPDATE SET
          tg_chat_id=excluded.tg_chat_id,
          remote_file_id=excluded.remote_file_id,
          file_unique_id=excluded.file_unique_id,
          file_name=excluded.file_name,
          mime_type=excluded.mime_type,
          file_size=excluded.file_size,
          parts=excluded.parts,
          virtual_folder=excluded.virtual_folder,
          upload_status=excluded.upload_status,
          uploaded_at=excluded.uploaded_at,
          last_synced_at=excluded.last_synced_at,
          checksum=excluded.checksum,
          notes=excluded.notes;
        """,
        {
            "tg_message_id": record.get("tg_message_id"),
            "tg_chat_id": record.get("tg_chat_id"),
            "remote_file_id": record.get("remote_file_id"),
            "file_unique_id": record.get("file_unique_id"),
            "file_name": record.get("file_name"),
            "mime_type": record.get("mime_type"),
            "file_size": record.get("file_size"),
            "parts": record.get("parts", 1),
            "virtual_folder": record.get("virtual_folder", "root"),
            "upload_status": record.get("upload_status", "uploaded"),
            "uploaded_at": record.get("uploaded_at"),
            "last_synced_at": record.get("last_synced_at"),
            "checksum": record.get("checksum"),
            "notes": record.get("notes"),
        },
    )
    conn.commit()
    row = conn.execute("SELECT id FROM files WHERE tg_message_id = ?", (record.get("tg_message_id"),)).fetchone()
    LOGGER.info(
        "upsert_file_record id=%s tg_message_id=%s upload_status=%s",
        row["id"] if row else None,
        record.get("tg_message_id"),
        record.get("upload_status", "uploaded"),
    )
    return int(row["id"])


def mark_deleted(conn: sqlite3.Connection, file_id: int, deleted_status: str = "deleted_remote") -> None:
    conn.execute("UPDATE files SET upload_status = ? WHERE id = ?", (deleted_status, file_id))
    conn.commit()
    LOGGER.info("mark_deleted file_id=%s status=%s", file_id, deleted_status)


def get_file_by_id(conn: sqlite3.Connection, file_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    return row


def search_files(
    conn: sqlite3.Connection,
    search: str = "",
    folder: str = "",
    page: int = 1,
    limit: int = 20,
) -> list[dict[str, Any]]:
    offset = max(page - 1, 0) * max(limit, 1)
    query = "SELECT * FROM files WHERE 1=1"
    params: list[Any] = []

    if search:
        query += " AND file_name LIKE ?"
        params.append(f"%{search}%")

    if folder:
        query += " AND virtual_folder = ?"
        params.append(folder)

    query += " ORDER BY uploaded_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, tuple(params)).fetchall()
    return rows


def create_job(
    conn: sqlite3.Connection,
    checksum: str | None,
    file_name: str | None,
    source_path: str | None,
    virtual_folder: str | None,
    status: str,
    error: str | None,
    created_at: str,
    updated_at: str,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO jobs (checksum, file_name, source_path, virtual_folder, status, error, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (checksum, file_name, source_path, virtual_folder, status, error, created_at, updated_at),
    )
    conn.commit()
    LOGGER.info("create_job id=%s status=%s file_name=%s", cur.lastrowid, status, file_name)
    return int(cur.lastrowid)


def update_job_status(conn: sqlite3.Connection, job_id: int, status: str, error: str | None, updated_at: str) -> None:
    conn.execute(
        "UPDATE jobs SET status = ?, error = ?, updated_at = ? WHERE id = ?",
        (status, error, updated_at, job_id),
    )
    conn.commit()
    LOGGER.info("update_job_status job_id=%s status=%s", job_id, status)


def get_job_by_id(conn: sqlite3.Connection, job_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return row


def list_jobs(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM jobs ORDER BY id DESC").fetchall()
    return rows


def find_file_by_checksum(conn: sqlite3.Connection, checksum: str) -> dict[str, Any] | None:
    return conn.execute("SELECT * FROM files WHERE checksum = ? LIMIT 1", (checksum,)).fetchone()


def get_last_indexed_message_id(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT MAX(tg_message_id) AS max_message_id FROM files").fetchone()
    if row is None or row["max_message_id"] is None:
        return 0
    return int(row["max_message_id"])


def mark_missing_messages_deleted(conn: sqlite3.Connection, existing_message_ids: set[int]) -> int:
    rows = conn.execute("SELECT id, tg_message_id, upload_status FROM files").fetchall()
    marked = 0
    for row in rows:
        if int(row["tg_message_id"]) not in existing_message_ids and row["upload_status"] != "deleted_remote":
            conn.execute("UPDATE files SET upload_status = ? WHERE id = ?", ("deleted_remote", row["id"]))
            marked += 1
    conn.commit()
    LOGGER.info("mark_missing_messages_deleted marked=%s", marked)
    return marked
