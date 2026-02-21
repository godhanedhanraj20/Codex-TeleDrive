from pathlib import Path

import pytest

from app import db
from app.queue_worker import QueueWorker
from tests.fixtures.fake_telegram import FakeFloodWaitError


@pytest.mark.asyncio
async def test_enqueue_upload_creates_job(db_conn, fake_telegram_client, tmp_path: Path):
    worker = QueueWorker(db_conn=db_conn, telegram_client=fake_telegram_client, upload_delay_seconds=0)
    await worker.start()

    file_path = tmp_path / "upload1.bin"
    file_path.write_bytes(b"hello")

    job_id = await worker.enqueue_upload(str(file_path), "upload1.bin", "docs")
    await worker.stop()

    job = db.get_job_by_id(db_conn, job_id)
    assert job is not None
    assert job["status"] == "queued"
    assert job["source_path"] == str(file_path)
    assert job["virtual_folder"] == "docs"


@pytest.mark.asyncio
async def test_duplicate_checksum_prevention(db_conn, fake_telegram_client, tmp_path: Path):
    worker = QueueWorker(db_conn=db_conn, telegram_client=fake_telegram_client, upload_delay_seconds=0)
    await worker.start()

    file_path_1 = tmp_path / "dup1.bin"
    file_path_2 = tmp_path / "dup2.bin"
    file_path_1.write_bytes(b"same-data")
    file_path_2.write_bytes(b"same-data")

    await worker.enqueue_upload(str(file_path_1), "dup1.bin", "docs")
    await worker._queue.join()

    with pytest.raises(ValueError):
        await worker.enqueue_upload(str(file_path_2), "dup2.bin", "docs")

    await worker.stop()


@pytest.mark.asyncio
async def test_queue_success_flow_marks_done_and_cleans_temp(db_conn, fake_telegram_client, tmp_path: Path):
    worker = QueueWorker(db_conn=db_conn, telegram_client=fake_telegram_client, upload_delay_seconds=0)
    await worker.start()

    file_path = tmp_path / "success.bin"
    file_path.write_bytes(b"content-success")

    job_id = await worker.enqueue_upload(str(file_path), "success.bin", "reports")
    await worker._queue.join()
    await worker.stop()

    job = db.get_job_by_id(db_conn, job_id)
    assert job["status"] == "done"
    assert not file_path.exists()

    stored = db_conn.execute("SELECT * FROM files WHERE checksum = ?", (job["checksum"],)).fetchone()
    assert stored is not None
    assert stored["virtual_folder"] == "reports"


@pytest.mark.asyncio
async def test_queue_failure_flow_marks_failed_and_cleans_temp(db_conn, fake_telegram_client, tmp_path: Path):
    fake_telegram_client.upload_should_fail = FakeFloodWaitError(9)
    worker = QueueWorker(db_conn=db_conn, telegram_client=fake_telegram_client, upload_delay_seconds=0)
    await worker.start()

    file_path = tmp_path / "fail.bin"
    file_path.write_bytes(b"content-fail")

    job_id = await worker.enqueue_upload(str(file_path), "fail.bin", "errors")
    await worker._queue.join()
    await worker.stop()

    job = db.get_job_by_id(db_conn, job_id)
    assert job["status"] == "failed"
    assert "flood_wait_seconds=9" in (job["error"] or "")
    assert not file_path.exists()


@pytest.mark.asyncio
async def test_retry_only_for_failed_jobs(db_conn, fake_telegram_client, tmp_path: Path, now_iso):
    worker = QueueWorker(db_conn=db_conn, telegram_client=fake_telegram_client, upload_delay_seconds=0)

    done_job_id = db.create_job(
        db_conn,
        checksum="c1",
        file_name="done.bin",
        source_path=str(tmp_path / "done.bin"),
        virtual_folder="root",
        status="done",
        error=None,
        created_at=now_iso,
        updated_at=now_iso,
    )

    failed_job_id = db.create_job(
        db_conn,
        checksum="c2",
        file_name="failed.bin",
        source_path=str(tmp_path / "failed.bin"),
        virtual_folder="root",
        status="failed",
        error="trace",
        created_at=now_iso,
        updated_at=now_iso,
    )

    with pytest.raises(ValueError):
        await worker.retry_failed_job(done_job_id)

    await worker.retry_failed_job(failed_job_id)
    failed_row = db.get_job_by_id(db_conn, failed_job_id)
    assert failed_row["status"] == "queued"
