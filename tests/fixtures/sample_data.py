from datetime import datetime, timezone

import pytest

from tests.fixtures.fake_telegram import FakeMedia, FakeMessage


@pytest.fixture
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture
def file_record(now_iso):
    return {
        "tg_message_id": 111,
        "tg_chat_id": 1,
        "remote_file_id": "file-id-111",
        "file_unique_id": "uniq-111",
        "file_name": "sample.txt",
        "mime_type": "text/plain",
        "file_size": 12,
        "parts": 1,
        "virtual_folder": "docs",
        "upload_status": "uploaded",
        "uploaded_at": now_iso,
        "last_synced_at": now_iso,
        "checksum": "abc123",
        "notes": None,
    }


@pytest.fixture
def media_message_factory():
    def _make(message_id: int, folder_tag: str = "root"):
        return FakeMessage(
            message_id=message_id,
            document=FakeMedia(
                file_id=f"fid-{message_id}",
                file_unique_id=f"uniq-{message_id}",
                file_name=f"{folder_tag}-{message_id}.bin",
                mime_type="application/octet-stream",
                file_size=message_id,
            ),
        )

    return _make


@pytest.fixture
def non_media_message_factory():
    def _make(message_id: int):
        return FakeMessage(message_id=message_id)

    return _make
