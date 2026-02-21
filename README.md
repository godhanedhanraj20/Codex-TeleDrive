# TeleDrive

TeleDrive is a localhost-only personal file utility that uses your **Telegram Saved Messages** as the remote storage backend and keeps a rebuildable **SQLite index** locally.

It provides a simple web dashboard to upload, list, download, delete, and resync files while keeping queue behavior predictable and transparent.

## Features

- **Telegram user-client storage** via Pyrogram (`chat_id="me"`, Saved Messages only)
- **Single-worker upload queue** with controlled delay and manual retry
- **Virtual folder support** (local organization in SQLite metadata)
- **Incremental and full resync** to reconcile local index with Telegram history
- **Single-page dashboard** (vanilla HTML/JS)
- **Structured JSON errors** with technical details
- **Operational logging** and startup temp-file cleanup

## Scope and Limitations

TeleDrive is intentionally limited to a strict personal/local scope:

- Localhost usage (`127.0.0.1`) for a single user
- Storage target is only Telegram **Saved Messages**
- No multi-user accounts, no public sharing links, no cloud deployment features
- No distributed queues or external services (Redis/Celery/etc.)
- No resumable downloads or file-splitting workflows

## Requirements

- Python **3.10+**
- Telegram API credentials:
  - `TG_API_ID`
  - `TG_API_HASH`
- Dependencies in `requirements.txt`:
  - `fastapi`
  - `uvicorn[standard]`
  - `pyrogram`
  - `aiofiles`
  - `python-multipart`
  - `pydantic`

## Installation

```bash
git clone <your-repo-url>
cd Codex-TeleDrive
python -m venv .venv
source .venv/bin/activate   # Windows (PowerShell): .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Configuration

Set environment variables in your shell before running TeleDrive.

Required:

```bash
export TG_API_ID=<your_telegram_api_id>
export TG_API_HASH=<your_telegram_api_hash>
```

Optional:

```bash
export APP_HOST=127.0.0.1
export APP_PORT=8000
export UPLOAD_CONCURRENCY=1
export UPLOAD_DELAY=2
```

You can place these in your shell profile (for example `~/.bashrc`) or export them directly in the same terminal session where you start the app.

## Run Locally

Start the server:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Open the dashboard:

- `http://127.0.0.1:8000`

Login flow (first run):

1. Send Telegram code from the dashboard/auth API using your phone number.
2. Submit code + `phone_code_hash` to sign in.
3. If your account has 2FA, submit password.
4. Session state is then shown as connected.

## Running Tests

Install test dependencies:

```bash
pip install pytest pytest-asyncio
```

Run:

```bash
pytest -q
```

Test coverage includes:

- SQLite schema initialization and DB helpers
- Job creation/status updates
- Queue behavior (enqueue, duplicate prevention, success/failure, retry rules, temp cleanup)
- Resync behavior (incremental filtering, full resync missing-message marking, non-media skipping, folder preservation)

## High-Level Folder Structure

```text
app/
  main.py               # FastAPI app lifecycle, startup/shutdown wiring, dashboard route
  db.py                 # SQLite schema + raw SQL helpers
  telegram_client.py    # Pyrogram user-client wrapper
  queue_worker.py       # Single-concurrency upload queue worker
  routes/
    auth.py             # Telegram login/status endpoints
    files.py            # Upload/list/download/delete/resync endpoints
    queue.py            # Queue listing and manual retry endpoints
  templates/
    index.html          # Single-page dashboard UI

data/                  # Runtime artifacts (db, session, temp files, logs)
tests/                 # Pytest suite for DB/queue/resync logic
requirements.txt       # Runtime Python dependencies
```

## Usage Examples

### Upload a file

From dashboard: choose file + folder, click upload.

API example:

```bash
curl -X POST "http://127.0.0.1:8000/api/files/upload" \
  -F "file=@/path/to/report.pdf" \
  -F "folder=docs"
```

### Retry a failed job

```bash
curl -X POST "http://127.0.0.1:8000/api/queue/42/retry"
```

### Run incremental resync

```bash
curl -X POST "http://127.0.0.1:8000/api/files/resync"
```

### Download a file by local index ID

```bash
curl -L "http://127.0.0.1:8000/api/files/5/download" -o downloaded.bin
```

## Troubleshooting & FAQ

### Telegram login fails

- Verify `TG_API_ID` and `TG_API_HASH` are correct and exported in the same shell.
- Make sure phone number is in international format (for example `+91...`).
- If sign-in reports password required, complete the 2FA step.

### `AUTH_REQUIRED` errors on file routes

The Telegram client is not connected yet. Complete auth flow (`send-code` → `sign-in` → optional `check-password`) first.

### Flood wait / rate-limit errors

TeleDrive records full technical error details in queue job error fields and logs. Wait the indicated seconds, then retry failed jobs manually.

### File not found during download/delete

The Telegram message may have been removed remotely. Run full resync to reconcile local index state.

## License

MIT License.

## Credits

- Telegram API ecosystem
- Pyrogram
- FastAPI
