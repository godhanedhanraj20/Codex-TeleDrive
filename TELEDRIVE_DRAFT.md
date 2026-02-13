# TeleDrive Draft — Telegram Saved Messages as Personal Cloud Storage

## 1) Idea Summary
Build a web app (**TeleDrive**) that uses a user’s Telegram account as a storage backend by uploading files to **Saved Messages** ("cloud chat").

Users can:
- Sign in with Telegram.
- Upload files from browser/mobile.
- Browse files in a gallery/list view.
- Preview/download/delete files.
- Organize content with folders/tags/search.

The app acts like a personal cloud drive UI, while Telegram stores the file objects.

---

## 2) Target User Value
- Reuse existing Telegram cloud storage behavior.
- Access files from a clean drive-like interface.
- Make media browsing easier than searching through chat history.
- Add organization features (metadata, tags, folders) not natively strong in chat view.

---

## 3) Core Scope (MVP)

### Authentication
- Telegram login flow (official and compliant).
- Session management in web app.

### File Upload
- Upload single/multiple files.
- Progress indicator + retry.
- Store each file in Saved Messages.
- Save metadata in app DB:
  - Telegram message ID
  - file name
  - MIME type
  - size
  - upload date
  - optional tags/folder

### File Browsing
- Grid gallery (images/video thumbs) + list mode.
- Sorting: newest, oldest, name, size.
- Search by name/tag.
- Basic filters: images, videos, docs, audio.

### File Actions
- Preview supported media.
- Download.
- Copy share link (if applicable).
- Delete (removes message and metadata).

---

## 4) Suggested Architecture

### Frontend
- React / Next.js (or similar).
- Components:
  - Login screen
  - Upload panel
  - File explorer (grid/list)
  - Preview modal/viewer
  - Settings page

### Backend API
- Node.js (Express/Fastify) or Python (FastAPI).
- Responsibilities:
  - Handle auth/session.
  - Interact with Telegram API client.
  - Store and query metadata.
  - Provide file listing/search endpoints.

### Telegram Integration Layer
- Use Telegram API libraries (MTProto-based clients).
- Upload files to Saved Messages chat.
- Read messages/media history for sync.
- Maintain mapping between app file records and Telegram message IDs.

### Database
- PostgreSQL / SQLite for MVP.
- Tables:
  - `users`
  - `files`
  - `tags`
  - `file_tags`
  - `sync_state`

---

## 5) Data Model (MVP)

### `files` table draft
- `id` (UUID)
- `user_id`
- `telegram_message_id`
- `telegram_chat_id` (self/saved messages)
- `name`
- `mime_type`
- `size_bytes`
- `uploaded_at`
- `updated_at`
- `folder` (nullable)
- `thumbnail_status`

---

## 6) Key User Flows

1. **Login**  
   User signs in with Telegram credentials via approved flow.

2. **Upload**  
   User selects files → backend uploads to Saved Messages → backend stores metadata → UI refreshes.

3. **View Gallery**  
   User opens app → backend returns indexed files → user browses/searches.

4. **Open File**  
   User clicks item → app fetches Telegram file stream/download endpoint.

5. **Delete File**  
   User deletes item → backend removes Telegram message → metadata removed or marked deleted.

---

## 7) Sync Strategy
- **Write-through on upload:** always persist metadata immediately after successful Telegram upload.
- **Background reconciliation job:**
  - Detect missing metadata for Telegram messages.
  - Detect orphaned metadata where message no longer exists.
- **Pagination/cursor sync** for large histories.

---

## 8) Security & Compliance Notes (Important)
- Use official Telegram auth methods and respect Telegram Terms of Service.
- Never store raw credentials in plaintext.
- Encrypt sensitive tokens/session data.
- Add per-user access isolation in DB/API.
- Rate-limit upload and API endpoints.
- Audit logging for file actions.

---

## 9) Non-Functional Requirements
- Handle large file uploads reliably (resume/retry where possible).
- Responsive UI for mobile + desktop.
- Reasonable performance for 10k+ files (indexed metadata + pagination).
- Graceful error handling for Telegram API outages/rate limits.

---

## 10) Future Features (Post-MVP)
- Folder tree + drag/drop organization.
- End-to-end encrypted file layer before upload.
- Public/private sharing abstraction.
- Desktop client (Electron/Tauri).
- Duplicate detection (hashing).
- AI search over file names/OCR metadata.

---

## 11) Suggested API Endpoints (Draft)
- `POST /auth/telegram/start`
- `POST /auth/telegram/verify`
- `POST /files/upload`
- `GET /files?query=&type=&sort=&page=`
- `GET /files/:id`
- `GET /files/:id/download`
- `DELETE /files/:id`
- `POST /files/:id/tags`
- `POST /sync/run`

---

## 12) Implementation Milestones
1. Project setup (frontend + backend + DB).
2. Telegram auth integration.
3. Upload to Saved Messages.
4. Metadata persistence.
5. Gallery/list UI.
6. Search/filter/sort.
7. Delete/download/preview actions.
8. Background sync + hardening.
9. Deployment + monitoring.

---

## 13) Open Questions to Finalize Before Build
- Which Telegram API stack will be used exactly?
- Expected file size limits for MVP?
- Do you need collaborative sharing, or only personal storage?
- Should app support only web first, or also mobile app in phase 1?
- What level of encryption is required beyond Telegram defaults?

---

## 14) One-Line Product Positioning
**TeleDrive is a personal cloud-drive interface powered by your Telegram Saved Messages storage, with better organization, search, and media browsing.**
