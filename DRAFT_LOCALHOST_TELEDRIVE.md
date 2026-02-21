# Draft: Localhost “TeleDrive” App (Pyrogram User Session + Telegram Saved Messages)

## Short answer
Yes — this is very doable **if implemented as a Telegram user client** (Pyrogram user session), not as a bot.

A localhost app can use **Saved Messages as private storage**:
- Upload file from your PC → send to your own Saved Messages (`chat_id="me"`).
- Index files locally in SQLite for fast listing/search.
- Download files back with streaming.

---

## 1) Product scope (corrected MVP)

### Goal
Build a local web app (`http://127.0.0.1:8000`) for one user that can:
1. Sign in to Telegram using Pyrogram user auth (phone + OTP + optional 2FA password).
2. Upload files to Saved Messages.
3. List/search files from local index.
4. Download files (streaming response).
5. Delete files and resync index.

### Critical constraint
- **Saved Messages requires a user session.** Do not use Bot API token flow for storage in Saved Messages.

---

## 2) Suggested stack

- **Backend:** Python + FastAPI
- **Telegram layer:** Pyrogram **user client** wrapper
- **Frontend:** HTML/JS (or Jinja templates)
- **DB:** SQLite
- **Server:** Uvicorn bound to `127.0.0.1`
- **Background jobs:** asyncio queue + worker(s)

---

## 3) Core architecture

1. **API layer**
   - Auth endpoints (`/api/auth/*`)
   - File endpoints (`/api/files/*`)
   - Queue/progress endpoints (`/api/queue/*`)

2. **Telegram service layer (Pyrogram user session)**
   - `send_document("me", ...)` for upload
   - `iter_history("me")` for resync/index rebuild
   - `download_media(...)` for download path/chunk flow
   - `delete_messages("me", ...)` for delete

3. **Queue layer (rate-limited worker)**
   - Uploads are enqueued and processed sequentially (default concurrency: 1)
   - FloodWait-aware retries (sleep Telegram-provided seconds)

4. **Index layer (SQLite)**
   - Message-to-file metadata map
   - Dedupe + reuse via Telegram `file_id`

5. **Frontend**
   - Upload panel, file table, queue status, retry/error visibility

---

## 4) Data model draft (SQLite)

```sql
CREATE TABLE files (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tg_message_id INTEGER NOT NULL UNIQUE,
  tg_chat_id INTEGER NOT NULL,
  remote_file_id TEXT,        -- Telegram file_id (reusable for re-send)
  file_unique_id TEXT,        -- Stable-ish Telegram file unique id
  file_name TEXT,
  mime_type TEXT,
  file_size INTEGER,
  parts INTEGER DEFAULT 1,    -- >1 when chunk-splitting used
  upload_status TEXT NOT NULL DEFAULT 'uploaded', -- queued/uploaded/failed/deleted
  uploaded_at TEXT NOT NULL,
  last_synced_at TEXT,
  checksum TEXT
);

CREATE INDEX idx_files_name ON files(file_name);
CREATE INDEX idx_files_uploaded_at ON files(uploaded_at);
CREATE INDEX idx_files_unique ON files(file_unique_id);
```

---

## 5) Upload/download constraints and policy

### File size policy
- Enforce max upload size of ~2 GB per Telegram file.
- Validate both client-side and server-side.
- If file >2 GB:
  - Option A (MVP): reject with clear message.
  - Option B: split into `.partNNN` chunks + manifest and upload parts.

### Rate-limit policy
- All uploads go through queue.
- On FloodWait / TooManyRequests:
  - sleep for server-provided wait seconds,
  - retry with capped retry count,
  - surface retry ETA in UI.

### Download policy
- Return FastAPI `StreamingResponse`.
- Avoid loading whole file in memory.
- Use temp file/chunk streaming for large files and cleanup after completion.

---

## 6) API draft (updated)

### Auth
- `POST /api/auth/send-code`
- `POST /api/auth/sign-in`
- `POST /api/auth/check-password`

### Files
- `GET /api/files?search=&page=`
- `POST /api/files/upload` → returns `queued` job
- `GET /api/files/{id}/download` → streaming response
- `DELETE /api/files/{id}`
- `POST /api/files/resync` (incremental)
- `POST /api/files/resync-full` (full rebuild)

### Queue/Jobs
- `GET /api/files/queued`
- `GET /api/queue/{job_id}`

### Optional split support
- `POST /api/files/split`
- `POST /api/files/assemble`

---

## 7) Sync strategy

### Incremental resync (default)
- Track latest processed timestamp/message id.
- Scan newer history only.
- Upsert records using `tg_message_id`, `remote_file_id`, `file_unique_id`.

### Full resync (manual)
- Paginate entire Saved Messages history.
- Rebuild/repair local index.
- Mark missing records as deleted/drifted.

---

## 8) Security baseline

- Bind app to `127.0.0.1` by default.
- Store Pyrogram session file with strict permissions.
- Protect secrets (`api_id`, `api_hash`) via env vars + optional OS keychain/encryption.
- Optional app passcode before showing dashboard.
- Conservative operation rate to reduce account risk.

---

## 9) Minimal folder structure

```text
teledrive/
  app/
    main.py
    telegram_client.py      # Pyrogram user client wrapper
    queue_worker.py         # rate-limited job worker
    db.py
    models.py
    routes/
      auth.py
      files.py
      queue.py
    static/
      app.js
      styles.css
    templates/
      index.html
  data/
    teledrive.db
    teledrive.session
  requirements.txt
  README.md
```

---

## 10) Phased plan

### Phase 1 (MVP)
- Pyrogram user auth flow
- Queued upload/list/download/delete
- 2GB limit enforcement
- Basic incremental resync

### Phase 2
- FloodWait metrics + better queue visibility
- Full resync and drift markers
- `file_id` reuse for duplicate uploads

### Phase 3
- Optional >2GB split/reassemble flow
- Range/resumable downloads
- Better metadata/tags/virtual folders

---

## 11) Final recommendation

Keep scope tight: single-user localhost, user-session auth, queue-backed uploads, streaming downloads, and robust resync.

This gives a practical “personal TeleDrive” without pretending to be full Google Drive parity.
