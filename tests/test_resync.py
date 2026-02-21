from types import SimpleNamespace

import pytest

from app import db
from app.routes.files import resync_full, resync_incremental


class DummyRequest:
    def __init__(self, db_conn, telegram_client):
        self.app = SimpleNamespace(
            state=SimpleNamespace(db_conn=db_conn, telegram_client=telegram_client)
        )


@pytest.mark.asyncio
async def test_incremental_resync_only_adds_newer_messages_and_skips_non_media(
    db_conn,
    fake_telegram_client,
    file_record,
    media_message_factory,
    non_media_message_factory,
):
    existing = dict(file_record)
    existing["tg_message_id"] = 100
    existing["virtual_folder"] = "kept-folder"
    db.upsert_file_record(db_conn, existing)

    fake_telegram_client.history_messages = [
        media_message_factory(90),
        non_media_message_factory(150),
        media_message_factory(160),
    ]

    response = await resync_incremental(DummyRequest(db_conn, fake_telegram_client))
    assert response.status_code == 200

    ids = {row["tg_message_id"] for row in db_conn.execute("SELECT tg_message_id FROM files").fetchall()}
    assert 90 not in ids
    assert 100 in ids
    assert 160 in ids


@pytest.mark.asyncio
async def test_full_resync_marks_missing_deleted_and_preserves_folder(
    db_conn,
    fake_telegram_client,
    file_record,
    media_message_factory,
):
    row1 = dict(file_record)
    row1["tg_message_id"] = 201
    row1["virtual_folder"] = "projects"
    row1["upload_status"] = "uploaded"

    row2 = dict(file_record)
    row2["tg_message_id"] = 202
    row2["virtual_folder"] = "archive"
    row2["upload_status"] = "uploaded"

    db.upsert_file_record(db_conn, row1)
    db.upsert_file_record(db_conn, row2)

    fake_telegram_client.history_messages = [media_message_factory(201)]

    response = await resync_full(DummyRequest(db_conn, fake_telegram_client))
    assert response.status_code == 200

    file_201 = db_conn.execute("SELECT * FROM files WHERE tg_message_id = 201").fetchone()
    file_202 = db_conn.execute("SELECT * FROM files WHERE tg_message_id = 202").fetchone()

    assert file_201["virtual_folder"] == "projects"
    assert file_201["upload_status"] == "uploaded"
    assert file_202["upload_status"] == "deleted_remote"


@pytest.mark.asyncio
async def test_full_resync_skips_non_media_messages(db_conn, fake_telegram_client, media_message_factory, non_media_message_factory):
    fake_telegram_client.history_messages = [
        non_media_message_factory(301),
        media_message_factory(302),
        non_media_message_factory(303),
    ]

    response = await resync_full(DummyRequest(db_conn, fake_telegram_client))
    assert response.status_code == 200

    ids = {row["tg_message_id"] for row in db_conn.execute("SELECT tg_message_id FROM files").fetchall()}
    assert 302 in ids
    assert 301 not in ids
    assert 303 not in ids
