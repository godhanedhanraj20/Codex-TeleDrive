from dataclasses import dataclass
from pathlib import Path

import pytest


@dataclass
class FakeMedia:
    file_id: str | None = None
    file_unique_id: str | None = None
    file_name: str | None = None
    mime_type: str | None = None
    file_size: int | None = None


@dataclass
class FakeChat:
    id: int


class FakeMessage:
    def __init__(
        self,
        message_id: int,
        chat_id: int = 1,
        *,
        document: FakeMedia | None = None,
        video: FakeMedia | None = None,
        audio: FakeMedia | None = None,
        photo: FakeMedia | None = None,
        voice: FakeMedia | None = None,
        animation: FakeMedia | None = None,
    ):
        self.id = message_id
        self.chat = FakeChat(chat_id)
        self.document = document
        self.video = video
        self.audio = audio
        self.photo = photo
        self.voice = voice
        self.animation = animation


class FakeTelegramClient:
    def __init__(self):
        self.started = True
        self.upload_should_fail: Exception | None = None
        self.uploaded_paths: list[str] = []
        self.upload_messages: list[FakeMessage] = []
        self.history_messages: list[FakeMessage] = []

    async def upload_file(self, path: str, caption: str | None = None):
        if self.upload_should_fail is not None:
            raise self.upload_should_fail
        self.uploaded_paths.append(path)
        if self.upload_messages:
            return self.upload_messages.pop(0)
        name = Path(path).name
        return FakeMessage(
            message_id=1000 + len(self.uploaded_paths),
            document=FakeMedia(
                file_id=f"fid-{name}",
                file_unique_id=f"uniq-{name}",
                file_name=name,
                mime_type="application/octet-stream",
                file_size=Path(path).stat().st_size,
            ),
        )

    async def iter_saved_messages(self, limit=None):
        count = 0
        for message in self.history_messages:
            if limit is not None and count >= limit:
                break
            count += 1
            yield message

    def extract_flood_wait_seconds(self, exc: Exception):
        return getattr(exc, "flood_wait_seconds", None)


class FakeFloodWaitError(Exception):
    def __init__(self, seconds: int):
        self.flood_wait_seconds = seconds
        super().__init__(f"Flood wait {seconds}")


@pytest.fixture
def fake_telegram_client() -> FakeTelegramClient:
    return FakeTelegramClient()
