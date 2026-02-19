# Draft: Localhost “TeleDrive” App (Pyrogram + Telegram Saved Messages)

## Short answer
Yes — this is very doable.

A simple localhost app can use **Telegram Saved Messages as storage**:
- Upload a file from your PC → send it to your own Saved Messages chat.
- List files by scanning your Saved Messages history.
- Download any file back to your PC.

This works like a lightweight personal cloud (Google Drive-style basics), with some trade-offs.

---

## 1) Product idea (MVP)

### Goal
Build a local web app (`http://localhost:8000`) that lets one user:
1. Authenticate with Telegram (via Pyrogram).
2. Upload files.
3. View file list (name, size, date, message id).
4. Download files.
5. Optionally delete files.

### What “Saved Messages as storage” means
- Every upload is a Telegram message containing a document/video/audio/photo.
- Metadata (filename, size, tags) can be inferred from message + optionally persisted in a small local DB.

---

## 2) Suggested stack

- **Backend:** Python + FastAPI
- **Telegram client:** Pyrogram
- **Frontend:** Simple HTML + JS (or Jinja templates first)
- **Local DB:** SQLite (for fast indexing/search, optional but recommended)
- **Server:** Uvicorn

Why this stack:
- FastAPI gives quick REST endpoints and easy localhost usage.
- Pyrogram handles upload/download to Telegram cleanly.
- SQLite avoids rescanning all messages on every page load.

---

## 3) Core architecture

### Components
1. **Web API Layer**
   - `/auth/start`, `/auth/verify`
   - `/files/upload`
   - `/files` (list/search)
   - `/files/{id}/download`
   - `/files/{id}` (delete)

2. **Telegram Service Layer (Pyrogram wrapper)**
   - `send_document` for uploads
   - `get_messages` / history scan for indexing
   - `download_media` for downloads
   - `delete_messages` for deletion

3. **Index Layer (SQLite)**
   - Store mapping: `telegram_message_id -> file metadata`
   - Fields: id, file_name, file_size, mime_type, upload_date, tg_message_id, file_unique_id

4. **Frontend**
   - One-page dashboard:
     - Upload form
     - File table with Download/Delete buttons
     - Search input

---

## 4) Data model draft (SQLite)

```sql
CREATE TABLE files (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tg_message_id INTEGER NOT NULL UNIQUE,
  tg_chat_id INTEGER NOT NULL,
  file_unique_id TEXT,
  file_id TEXT,
  file_name TEXT,
  mime_type TEXT,
  file_size INTEGER,
  uploaded_at TEXT NOT NULL,
  local_tag TEXT,
  checksum TEXT
);

CREATE INDEX idx_files_name ON files(file_name);
CREATE INDEX idx_files_uploaded_at ON files(uploaded_at);
```

---

## 5) MVP flow

1. User opens localhost app.
2. If no session exists, app asks for Telegram login (phone + OTP, maybe 2FA password).
3. User uploads a file.
4. Backend sends file to Saved Messages using Pyrogram.
5. Backend stores metadata in SQLite.
6. File appears in list.
7. User clicks download; backend streams from Telegram to browser.

---

## 6) Key technical concerns

1. **Large file limits**
   - Telegram has size limits depending on account/app capabilities.
   - Need clear UI errors for oversize files.

2. **Rate limits / flood waits**
   - Bulk operations can trigger Telegram flood waits.
   - Add retry/backoff and queue uploads.

3. **Session security**
   - Pyrogram session file must be protected.
   - For local app: store session in app directory with strict permissions.

4. **Index sync**
   - DB can drift if messages are deleted from Telegram directly.
   - Add “Resync” button to rebuild index from Saved Messages history.

5. **Privacy/security**
   - Localhost only by default (`127.0.0.1`).
   - Optional app passcode to open UI.

---

## 7) Suggested API draft

- `POST /api/auth/send-code`
- `POST /api/auth/sign-in`
- `POST /api/auth/check-password`
- `GET /api/files?search=&page=`
- `POST /api/files/upload`
- `GET /api/files/{id}/download`
- `DELETE /api/files/{id}`
- `POST /api/files/resync`

---

## 8) Minimal folder structure

```text
teledrive/
  app/
    main.py              # FastAPI entry
    telegram_client.py   # Pyrogram wrapper
    db.py                # sqlite setup + queries
    models.py            # pydantic schemas
    routes/
      auth.py
      files.py
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

## 9) Phase plan

### Phase 1 (1–2 days)
- Telegram auth
- Upload + list + download
- Basic UI

### Phase 2
- Delete support
- Search/sort/pagination
- Resync index

### Phase 3
- Upload queue + progress bars
- Folder/tag abstraction (virtual folders in DB)
- Share/export metadata

---

## 10) Honest comparison with Google Drive

### Good
- Simple personal cloud behavior
- Works with your existing Telegram account
- No extra infra costs for basic personal usage

### Not the same as Drive
- No native folder tree (must emulate in metadata)
- Telegram constraints (rate limits, file rules)
- Not ideal for team collaboration/versioning

---

## 11) Recommendation

Start with a strict MVP:
- single-user localhost app,
- Saved Messages only,
- upload/list/download/delete,
- SQLite index + resync.

If this feels smooth, then add virtual folders and better UX.

This keeps scope realistic and gives a working “personal TeleDrive” quickly.
