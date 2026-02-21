import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Optional stub to keep imports stable when pyrogram is unavailable.
if "pyrogram" not in sys.modules:
    pyrogram = types.ModuleType("pyrogram")

    class _DummyClient:  # pragma: no cover
        pass

    pyrogram.Client = _DummyClient

    errors = types.ModuleType("pyrogram.errors")

    class FloodWait(Exception):
        def __init__(self, value: int):
            self.value = value
            super().__init__(f"Flood wait: {value}")

    errors.FloodWait = FloodWait

    types_mod = types.ModuleType("pyrogram.types")

    class Message:  # pragma: no cover
        pass

    types_mod.Message = Message

    sys.modules["pyrogram"] = pyrogram
    sys.modules["pyrogram.errors"] = errors
    sys.modules["pyrogram.types"] = types_mod

pytest_plugins = [
    "tests.fixtures.db",
    "tests.fixtures.fake_telegram",
    "tests.fixtures.sample_data",
]

# Compatibility shim for fastapi.background.BackgroundTask used by app.routes.files.
try:
    import fastapi.background as _fastapi_background
    from starlette.background import BackgroundTask as _StarletteBackgroundTask

    if not hasattr(_fastapi_background, "BackgroundTask"):
        _fastapi_background.BackgroundTask = _StarletteBackgroundTask
except Exception:
    pass
