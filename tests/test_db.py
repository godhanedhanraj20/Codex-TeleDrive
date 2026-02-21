from app import db


def test_initialize_database_creates_schema(db_conn):
    file_columns = {row["name"] for row in db_conn.execute("PRAGMA table_info(files)").fetchall()}
    jobs_columns = {row["name"] for row in db_conn.execute("PRAGMA table_info(jobs)").fetchall()}

    assert {
        "id",
        "tg_message_id",
        "tg_chat_id",
        "remote_file_id",
        "file_unique_id",
        "file_name",
        "mime_type",
        "file_size",
        "parts",
        "virtual_folder",
        "upload_status",
        "uploaded_at",
        "last_synced_at",
        "checksum",
        "notes",
    }.issubset(file_columns)
    assert {
        "id",
        "checksum",
        "file_name",
        "source_path",
        "virtual_folder",
        "status",
        "error",
        "created_at",
        "updated_at",
    }.issubset(jobs_columns)


def test_upsert_file_record_updates_existing_row(db_conn, file_record):
    file_id = db.upsert_file_record(db_conn, file_record)
    assert isinstance(file_id, int)

    updated = dict(file_record)
    updated["file_name"] = "renamed.txt"
    updated["virtual_folder"] = "archives"
    updated["upload_status"] = "uploaded"
    file_id_2 = db.upsert_file_record(db_conn, updated)

    assert file_id == file_id_2
    row = db_conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    assert row["file_name"] == "renamed.txt"
    assert row["virtual_folder"] == "archives"


def test_create_job_and_status_transition(db_conn, now_iso):
    job_id = db.create_job(
        db_conn,
        checksum="checksum-1",
        file_name="upload.bin",
        source_path="/tmp/upload.bin",
        virtual_folder="docs",
        status="queued",
        error=None,
        created_at=now_iso,
        updated_at=now_iso,
    )

    row = db.get_job_by_id(db_conn, job_id)
    assert row["status"] == "queued"
    assert row["virtual_folder"] == "docs"

    db.update_job_status(db_conn, job_id=job_id, status="uploading", error=None, updated_at=now_iso)
    row = db.get_job_by_id(db_conn, job_id)
    assert row["status"] == "uploading"


def test_mark_missing_messages_deleted_respects_existing_deleted(db_conn, file_record):
    first = dict(file_record)
    first["tg_message_id"] = 2001
    first["upload_status"] = "uploaded"
    second = dict(file_record)
    second["tg_message_id"] = 2002
    second["upload_status"] = "deleted_remote"

    db.upsert_file_record(db_conn, first)
    db.upsert_file_record(db_conn, second)

    marked = db.mark_missing_messages_deleted(db_conn, existing_message_ids={2002})
    assert marked == 1

    statuses = {
        row["tg_message_id"]: row["upload_status"]
        for row in db_conn.execute("SELECT tg_message_id, upload_status FROM files").fetchall()
    }
    assert statuses[2001] == "deleted_remote"
    assert statuses[2002] == "deleted_remote"


def test_folder_persistence_in_file_records(db_conn, file_record):
    file_record["virtual_folder"] = "projects"
    db.upsert_file_record(db_conn, file_record)

    row = db.search_files(db_conn, folder="projects", page=1, limit=10)
    assert len(row) == 1
    assert row[0]["virtual_folder"] == "projects"
