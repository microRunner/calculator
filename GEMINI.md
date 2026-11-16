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

## 4. Google Play Store Release Status & Next Steps
- **Package ID:** `io.github.microrunner.calculator` (`android/twa-manifest.json`), bundle at `android/app-release-bundle.aab`.
- **Completed:**
  - Data safety CSV generated at `/mnt/chromeos/MyFiles/Downloads/data_safety_cloud_calculator.csv` (uses `https://cloud-calculator-570480688616.us-central1.run.app/privacy`).
  - Store visual assets generated in `android/store_assets/` (and copied to `/mnt/chromeos/MyFiles/Downloads/play_store_assets/`): 512×512 icon, 1024×500 feature graphic, phone (1080×1920), 7" tablet (1200×1920), and 10" tablet (1600×2560) screenshots.
  - Play App Signing SHA-256 (`A3:13:4C:A6:62:83:AD:F9:BF:F4:8A:10:A6:8D:87:E2:B8:13:92:6F:CB:8B:07:8A:94:40:72:58:AB:F8:9B:0A`) + upload key SHA-256 (`B6:36:...`) added to `deploy_cloud_run.sh` and live on Cloud Run `/.well-known/assetlinks.json`.
- **Next Steps to Reach Production:**
  1. Finish remaining Play Console checklist items (**Data safety** CSV import, **Government apps = No**, **Financial features = No**, **Main store listing** assets/descriptions).
  2. Test on a real Android phone via **Internal testing** (reinstall if previously installed) to confirm full-screen TWA (no URL bar) and Google Sign-In.
  3. Promote to **Closed testing** and run for **14 continuous days with 12+ opted-in testers** (required for Personal accounts; need 4+ more testers beyond the 8 existing Firestore users).
  4. Click **Apply for production** on the Play Console Dashboard, then submit a **Production** release for Google review.

