from pathlib import Path

import pytest

from app.db import get_connection, initialize_database


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_teledrive.db"


@pytest.fixture
def db_conn(temp_db_path: Path):
    conn = get_connection(temp_db_path)
    initialize_database(conn)
    try:
        yield conn
    finally:
        conn.close()
