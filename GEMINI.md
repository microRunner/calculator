# Cloud Calculator Workspace Rules

## 1. Local Development Server & Port
- **Always use port `8000`** when running the local server (`http://localhost:8000`). **Never use port `8080`** locally.
- Google OAuth 2.0 (`GOOGLE_CLIENT_ID`) only authorizes `http://localhost:8000` for local sign-in; running on any other port triggers `Error 400: origin_mismatch`.
- Always use the project virtual environment (`./venv/bin/python` or `./venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --reload`).

## 2. Firestore (`calculatordb`) & History Synchronization
- Every user calculation or history mutation (create, delete item, clear all) must synchronize with both client `localStorage` and backend Firestore (`users/{email}/history` and `calculation_count` in `calculatordb`).
- When a user deletes or clears history items, those items must be deleted from Firestore so they do not auto-restore or appear in Admin calculation logs.
- If a signed-in user's Firestore history is empty (`[]`), `/api/history` must return `[]` rather than falling back to the shared in-memory `history_db`.

## 3. Google OAuth & Avatar Rendering
- All `<img>` tags displaying Google profile pictures (`lh3.googleusercontent.com`) must include `referrerpolicy="no-referrer"` to prevent HTTP 403/429 blocks on `http://localhost:8000`.
- Admin dashboard and metrics (`/admin`, `/api/admin/summary`, `/api/users`) are strictly restricted to `rahilgupta017@gmail.com`.
