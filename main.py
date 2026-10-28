import ast
import operator
import math
import os
import json
from typing import List, Optional
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from google.cloud import firestore

app = FastAPI(
    title="Cloud Calculator",
    description="A responsive calculator web application designed for Google Cloud Run",
    version="1.0.0"
)

GOOGLE_CLIENT_ID = os.environ.get(
    "GOOGLE_CLIENT_ID",
    "570480688616-1kfggobt8nu318kktd8ao689u6pmln6s.apps.googleusercontent.com"
)
GCP_PROJECT = os.environ.get("GCP_PROJECT", "chess-analyzer-497918")
FIRESTORE_DATABASE = os.environ.get("FIRESTORE_DATABASE", "calculatordb")
ADMIN_EMAILS = {
    e.strip().lower()
    for e in os.environ.get("ADMIN_EMAILS", "rahilgupta017@gmail.com").split(",")
    if e.strip()
}

# Initialize Firestore Client
firestore_client = None
try:
    firestore_client = firestore.Client(project=GCP_PROJECT, database=FIRESTORE_DATABASE)
    print(f"Connected to Firestore database '{FIRESTORE_DATABASE}' in project '{GCP_PROJECT}'")
except Exception as e:
    print(f"Warning: Could not connect to Firestore ({e}). Using in-memory fallback.")

# Safe math operators and functions
SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

SAFE_FUNCTIONS = {
    "sqrt": math.sqrt,
    "abs": abs,
    "round": round,
}

class CalculationRequest(BaseModel):
    expression: str
    email: Optional[str] = None

class UserSyncRequest(BaseModel):
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None

class CalculationResponse(BaseModel):
    expression: str
    result: float | int
    display_result: str
    timestamp: str

class CalculationHistoryItem(BaseModel):
    id: int
    expression: str
    result: str
    timestamp: str

# In-memory history (last 100 items)
history_db: List[CalculationHistoryItem] = []
history_counter = 0

# In-memory user tracking
users_db: dict = {}  # email -> {name, email, picture, first_seen, last_seen, login_count}

def safe_eval(node):
    if isinstance(node, ast.Expression):
        return safe_eval(node.body)
    elif isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("Invalid constant type in expression")
    elif isinstance(node, ast.BinOp):
        left = safe_eval(node.left)
        right = safe_eval(node.right)
        op_type = type(node.op)
        if op_type in SAFE_OPERATORS:
            if op_type == ast.Div and right == 0:
                raise ZeroDivisionError("Division by zero")
            return SAFE_OPERATORS[op_type](left, right)
        raise ValueError(f"Unsupported operator: {op_type.__name__}")
    elif isinstance(node, ast.UnaryOp):
        operand = safe_eval(node.operand)
        op_type = type(node.op)
        if op_type in SAFE_OPERATORS:
            return SAFE_OPERATORS[op_type](operand)
        raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
    elif isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in SAFE_FUNCTIONS:
            args = [safe_eval(arg) for arg in node.args]
            return SAFE_FUNCTIONS[node.func.id](*args)
        raise ValueError(f"Unsupported function call")
    else:
        raise ValueError("Invalid syntax in expression")

def clean_expression(expr: str) -> str:
    """Normalize symbols to Python-parseable math string."""
    cleaned = expr.replace("×", "*").replace("✕", "*").replace("X", "*").replace("x", "*")
    cleaned = cleaned.replace("÷", "/")
    cleaned = cleaned.replace("−", "-")
    cleaned = cleaned.replace("√", "sqrt")
    # Handle sqrt number syntax e.g. sqrt9 -> sqrt(9)
    import re
    cleaned = re.sub(r'sqrt\s*(\d+(\.\d+)?)', r'sqrt(\1)', cleaned)
    return cleaned

@app.get("/health")
def health_check():
    """GCP Cloud Run health check endpoint"""
    return {"status": "healthy", "service": "calculator", "timestamp": datetime.utcnow().isoformat()}

def persist_calculation_async(email: str, raw_expr: str, display: str, timestamp_str: str, now_iso: str):
    """Write calculation and user stats to Firestore asynchronously in the background."""
    if not firestore_client:
        return
    try:
        user_ref = firestore_client.collection("users").document(email)
        user_ref.set({
            "email": email,
            "calculation_count": firestore.Increment(1),
            "last_active": now_iso
        }, merge=True)
        user_ref.collection("history").add({
            "expression": raw_expr,
            "result": display,
            "timestamp": timestamp_str,
            "created_at": firestore.SERVER_TIMESTAMP,
        })
    except Exception as f_err:
        print(f"Async Firestore calculation error: {f_err}")

@app.post("/api/calculate", response_model=CalculationResponse)
def calculate(req: CalculationRequest, background_tasks: BackgroundTasks):
    global history_counter
    raw_expr = req.expression.strip()
    if not raw_expr:
        raise HTTPException(status_code=400, detail="Expression cannot be empty")
    
    cleaned = clean_expression(raw_expr)
    try:
        parsed = ast.parse(cleaned, mode="eval")
        res = safe_eval(parsed)
        
        # Format display result
        if isinstance(res, float) and res.is_integer():
            final_res = int(res)
            display = str(final_res)
        elif isinstance(res, float):
            final_res = round(res, 8)
            display = f"{final_res:g}"
        else:
            final_res = res
            display = str(res)
            
        timestamp_str = datetime.now().strftime("%H:%M:%S")
        
        # Save to history
        history_counter += 1
        history_item = CalculationHistoryItem(
            id=history_counter,
            expression=raw_expr,
            result=display,
            timestamp=timestamp_str
        )
        history_db.insert(0, history_item)
        if len(history_db) > 100:
            history_db.pop()

        # Track usage per user (in-memory update is sub-millisecond)
        now_iso = datetime.utcnow().isoformat()
        if req.email and req.email in users_db:
            users_db[req.email]["calculation_count"] = users_db[req.email].get("calculation_count", 0) + 1
            users_db[req.email]["last_active"] = now_iso

        # Dispatch Firestore database write in background so user receives result instantly
        if firestore_client and req.email:
            background_tasks.add_task(
                persist_calculation_async,
                req.email,
                raw_expr,
                display,
                timestamp_str,
                now_iso
            )
            
        return CalculationResponse(
            expression=raw_expr,
            result=final_res,
            display_result=display,
            timestamp=timestamp_str
        )
    except ZeroDivisionError:
        raise HTTPException(status_code=400, detail="Cannot divide by zero")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid expression: {str(e)}")

@app.get("/api/history")
def get_history(email: Optional[str] = None):
    if firestore_client and email:
        try:
            docs = (
                firestore_client.collection("users")
                .document(email)
                .collection("history")
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(100)
                .stream()
            )
            items = []
            for idx, doc in enumerate(docs):
                d = doc.to_dict()
                items.append({
                    "id": d.get("id", idx + 1),
                    "expression": d.get("expression", ""),
                    "result": str(d.get("result", "")),
                    "timestamp": d.get("timestamp", "")
                })
            if items:
                return items
        except Exception as e:
            print(f"Firestore get_history error: {e}")
    return history_db

@app.delete("/api/history/{item_id}")
def delete_history_item(item_id: int):
    global history_db
    initial_len = len(history_db)
    history_db = [item for item in history_db if item.id != item_id]
    if len(history_db) == initial_len:
        raise HTTPException(status_code=404, detail="History item not found")
    return {"status": "deleted", "id": item_id}

@app.delete("/api/history")
def clear_history():
    global history_db
    history_db.clear()
    return {"status": "cleared"}

@app.post("/api/auth/google")
async def google_auth(request: Request):
    """Verify Google Sign-In token and track user."""
    try:
        body = await request.json()
        credential = body.get("credential")
        if not credential:
            raise HTTPException(status_code=401, detail="Invalid Google token")

        idinfo = id_token.verify_oauth2_token(
            credential, google_requests.Request(), GOOGLE_CLIENT_ID
        )

        email = idinfo.get("email", "")
        name = idinfo.get("name", "")
        picture = idinfo.get("picture", "")

        now = datetime.utcnow().isoformat()

        if email in users_db:
            users_db[email]["last_seen"] = now
            users_db[email]["login_count"] += 1
            users_db[email]["name"] = name
            users_db[email]["picture"] = picture
        else:
            users_db[email] = {
                "name": name,
                "email": email,
                "picture": picture,
                "first_seen": now,
                "last_seen": now,
                "login_count": 1,
                "calculation_count": 0,
                "last_active": now,
            }

        # Sync user profile to Firestore
        if firestore_client:
            try:
                user_ref = firestore_client.collection("users").document(email)
                doc = user_ref.get()
                if doc.exists:
                    user_ref.update({
                        "name": name,
                        "picture": picture,
                        "last_seen": now,
                        "login_count": firestore.Increment(1),
                    })
                    # Sync back state to in-memory cache
                    d = doc.to_dict()
                    users_db[email]["login_count"] = d.get("login_count", 1) + 1
                    users_db[email]["calculation_count"] = d.get("calculation_count", 0)
                    users_db[email]["first_seen"] = d.get("first_seen", now)
                else:
                    user_ref.set(users_db[email])
            except Exception as f_err:
                print(f"Firestore user auth sync error: {f_err}")

        return {
            "status": "success",
            "user": {"name": name, "email": email, "picture": picture},
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Google token")

@app.get("/api/auth/client-id")
def get_client_id():
    """Return the Google OAuth Client ID to the frontend."""
    return {"client_id": GOOGLE_CLIENT_ID}

@app.post("/api/auth/sync")
def sync_user(req: UserSyncRequest):
    """Sync client-side session to ensure Firestore profile is up to date."""
    now = datetime.utcnow().isoformat()
    if req.email in users_db:
        if req.name:
            users_db[req.email]["name"] = req.name
        if req.picture:
            users_db[req.email]["picture"] = req.picture
    else:
        users_db[req.email] = {
            "name": req.name or req.email.split("@")[0],
            "email": req.email,
            "picture": req.picture or "",
            "first_seen": now,
            "last_seen": now,
            "login_count": 1,
            "calculation_count": 0,
            "last_active": now,
        }

    if firestore_client:
        try:
            user_ref = firestore_client.collection("users").document(req.email)
            payload = {
                "email": req.email,
                "name": req.name or req.email.split("@")[0],
                "last_seen": now,
            }
            if req.picture:
                payload["picture"] = req.picture
            user_ref.set(payload, merge=True)
        except Exception as e:
            print(f"Firestore sync_user error: {e}")
    return {"status": "synced"}

def fetch_all_users():
    """Fetch users from Firestore with fallback to in-memory users_db."""
    if firestore_client:
        try:
            docs = firestore_client.collection("users").stream()
            db_users = {}
            for d in docs:
                data = d.to_dict()
                email = data.get("email") or d.id
                data["email"] = email
                if not data.get("name") or data["name"] == "Anonymous":
                    data["name"] = email.split("@")[0]
                db_users[email] = data

            # Merge with in-memory if any newer data exists
            for email, data in users_db.items():
                if email not in db_users:
                    db_users[email] = data
                else:
                    if not db_users[email].get("name") and data.get("name"):
                        db_users[email]["name"] = data["name"]
                    if not db_users[email].get("picture") and data.get("picture"):
                        db_users[email]["picture"] = data["picture"]
            return list(db_users.values())
        except Exception as e:
            print(f"Firestore fetch_all_users error: {e}")
    return list(users_db.values())

@app.get("/api/users")
def get_users(email: Optional[str] = None):
    """Admin endpoint to see all users who have signed in (Admin only)."""
    if not email or email.strip().lower() not in ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="Forbidden: Admin access restricted to rahilgupta017@gmail.com")
    return fetch_all_users()

@app.get("/api/users/{target_email}/calculations")
def get_user_calculations(target_email: str, email: Optional[str] = None):
    """Admin endpoint to get all calculations for a specific user (Admin or self)."""
    if not email or (email.strip().lower() not in ADMIN_EMAILS and email.strip().lower() != target_email.strip().lower()):
        raise HTTPException(status_code=403, detail="Forbidden: Admin access required.")
    if firestore_client:
        try:
            docs = (
                firestore_client.collection("users")
                .document(target_email)
                .collection("history")
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(100)
                .stream()
            )
            return [doc.to_dict() for doc in docs]
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    return []

def is_within_7_days(date_val):
    """Check if date or ISO timestamp string is within the last 7 days."""
    if not date_val:
        return False
    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(days=7)
    try:
        if isinstance(date_val, datetime):
            d = date_val if date_val.tzinfo else date_val.replace(tzinfo=timezone.utc)
            return d >= cutoff
        elif isinstance(date_val, str):
            clean_str = date_val.replace("Z", "+00:00")
            d = datetime.fromisoformat(clean_str)
            if not d.tzinfo:
                d = d.replace(tzinfo=timezone.utc)
            return d >= cutoff
    except Exception:
        pass
    return False

def calculate_admin_metrics(users_list):
    """Compute lifetime and last-7-day aggregate metrics."""
    total_lifetime_users = len(users_list)
    total_lifetime_sessions = sum(u.get("login_count", 1) for u in users_list)
    total_lifetime_calculations = sum(u.get("calculation_count", len(u.get("calculations", []))) for u in users_list)

    active_users_7d = 0
    sessions_7d = 0
    calcs_7d = 0

    for u in users_list:
        is_active = (
            is_within_7_days(u.get("last_active"))
            or is_within_7_days(u.get("last_seen"))
            or is_within_7_days(u.get("first_seen"))
        )
        if is_active:
            active_users_7d += 1
            sessions_7d += u.get("login_count", 1)

        for c in u.get("calculations", []):
            if is_within_7_days(c.get("created_at")) or is_within_7_days(c.get("timestamp")):
                calcs_7d += 1

    return {
        "lifetime": {
            "total_users": total_lifetime_users,
            "total_sessions": total_lifetime_sessions,
            "total_calculations": total_lifetime_calculations,
        },
        "last_7_days": {
            "active_users": active_users_7d,
            "sessions": sessions_7d,
            "calculations": calcs_7d,
        }
    }

@app.get("/api/admin/summary")
def get_admin_summary(email: Optional[str] = None):
    """Consolidated endpoint returning all users, calculations, and lifetime/7d metrics (Admin only)."""
    if not email or email.strip().lower() not in ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="Forbidden: Admin access restricted to rahilgupta017@gmail.com")

    all_users = fetch_all_users()
    summary = []
    for u in all_users:
        u_email = u.get("email", "")
        calcs = []
        if firestore_client and u_email:
            try:
                c_docs = (
                    firestore_client.collection("users")
                    .document(u_email)
                    .collection("history")
                    .order_by("created_at", direction=firestore.Query.DESCENDING)
                    .limit(50)
                    .stream()
                )
                for cd in c_docs:
                    d = cd.to_dict()
                    c_at = d.get("created_at")
                    c_at_str = c_at.isoformat() if hasattr(c_at, "isoformat") else (str(c_at) if c_at else None)
                    calcs.append({
                        "expression": d.get("expression", ""),
                        "result": str(d.get("result", "")),
                        "timestamp": d.get("timestamp", ""),
                        "created_at": c_at_str,
                    })
            except Exception as e:
                print(f"Error fetching user calcs for summary: {e}")
        user_info = dict(u)
        user_info["calculations"] = calcs
        user_info["calculation_count"] = len(calcs) if calcs else u.get("calculation_count", 0)
        summary.append(user_info)

    summary.sort(key=lambda x: x.get("last_active", x.get("last_seen", "")), reverse=True)
    metrics = calculate_admin_metrics(summary)
    return {
        "metrics": metrics,
        "users": summary
    }

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(email: Optional[str] = None):
    """Simple admin dashboard to view signed-in users, calculations, and metrics (Admin only)."""
    if not email or email.strip().lower() not in ADMIN_EMAILS:
        return HTMLResponse(
            status_code=403,
            content="""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>403 - Access Denied</title>
  <style>
    body { font-family: -apple-system, sans-serif; background: #0f172a; color: #f8fafc; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
    .card { background: #1e293b; border: 1px solid #334155; border-radius: 16px; padding: 2.5rem; text-align: center; max-width: 440px; box-shadow: 0 20px 40px rgba(0,0,0,0.5); }
    h1 { color: #ef4444; font-size: 1.6rem; margin-top: 0; }
    p { color: #94a3b8; font-size: 0.95rem; line-height: 1.5; }
    a { display: inline-block; margin-top: 1.25rem; background: #38bdf8; color: #0f172a; text-decoration: none; padding: 0.6rem 1.25rem; border-radius: 8px; font-weight: 600; font-size: 0.9rem; }
  </style>
</head>
<body>
  <div class="card">
    <div style="font-size:3rem;margin-bottom:0.5rem;">🔒</div>
    <h1>Access Restricted</h1>
    <p>The administrative dashboard and metrics are restricted exclusively to authorized administrators.</p>
    <a href="/">← Return to Calculator</a>
  </div>
</body>
</html>"""
        )

    data = get_admin_summary(email=email)
    users = data["users"]
    m = data["metrics"]
    lt = m["lifetime"]
    w7 = m["last_7_days"]

    rows_html = ""
    for u in users:
        email = u.get("email", "")
        avatar = f'<img src="{u.get("picture", "")}" style="width:32px;height:32px;border-radius:50%;vertical-align:middle;margin-right:8px;" />' if u.get("picture") else "👤 "
        calcs = u.get("calculations", [])
        calc_count = u.get("calculation_count", len(calcs))

        calcs_html = ""
        if calcs:
            items_li = "".join([
                f"""<li style="margin-bottom:0.4rem;display:flex;justify-content:space-between;gap:1rem;">
                    <span><strong style="color:#f8fafc;">{c.get('expression', '')}</strong> = <span style="color:#38bdf8;">{c.get('result', '')}</span></span>
                    <span style="color:#64748b;font-size:0.75rem;">{c.get('timestamp', '')}</span>
                </li>""" for c in calcs
            ])
            calcs_html = f"""
            <details class="calc-dropdown">
              <summary><span class="badge count">{calc_count} calculations</span> <span style="font-size:0.75rem;cursor:pointer;color:#38bdf8;">▸ View Log</span></summary>
              <ul class="calc-list" style="margin:0.5rem 0 0;padding:0.75rem 1rem;background:#0f172a;border-radius:8px;list-style:none;max-height:160px;overflow-y:auto;border:1px solid #334155;">
                {items_li}
              </ul>
            </details>
            """
        else:
            calcs_html = f'<span class="badge">0</span>'

        rows_html += f"""
        <tr>
          <td>{avatar}<strong>{u.get('name', 'Anonymous')}</strong></td>
          <td><code>{email}</code></td>
          <td style="text-align:center;"><span class="badge">{u.get('login_count', 0)}</span></td>
          <td>{calcs_html}</td>
          <td style="color:#94a3b8;font-size:0.85rem;">{u.get('first_seen', '-')}</td>
          <td style="color:#94a3b8;font-size:0.85rem;">{u.get('last_active', u.get('last_seen', '-'))}</td>
        </tr>
        """
    if not users:
        rows_html = '<tr><td colspan="6" style="text-align:center;padding:2rem;color:#64748b;">No users have signed in yet.</td></tr>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Cloud Calculator - User Activity</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #0f172a;
      color: #f8fafc;
      margin: 0;
      padding: 2rem;
    }}
    .container {{
      max-width: 1040px;
      margin: 0 auto;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 1.5rem;
      border-bottom: 1px solid #334155;
      padding-bottom: 1rem;
    }}
    h1 {{ margin: 0; font-size: 1.5rem; }}
    a.btn {{
      background: #38bdf8;
      color: #0f172a;
      text-decoration: none;
      padding: 0.5rem 1rem;
      border-radius: 8px;
      font-weight: 600;
      font-size: 0.85rem;
    }}
    .metrics-section {{
      margin-bottom: 2rem;
    }}
    .metrics-group-title {{
      font-size: 0.8rem;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: #94a3b8;
      margin: 1rem 0 0.5rem;
    }}
    .metrics-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 1rem;
      margin-bottom: 1rem;
    }}
    .metric-card {{
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 12px;
      padding: 1rem 1.25rem;
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
      box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    }}
    .metric-card.recent {{
      border-color: #0369a1;
      background: linear-gradient(145deg, #1e293b 0%, #0c2d48 100%);
    }}
    .metric-label {{
      font-size: 0.78rem;
      color: #94a3b8;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .metric-val {{
      font-size: 1.8rem;
      font-weight: 700;
      color: #f8fafc;
    }}
    .metric-card.recent .metric-val {{
      color: #38bdf8;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: #1e293b;
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    }}
    th, td {{
      padding: 1rem 1.25rem;
      text-align: left;
      border-bottom: 1px solid #334155;
      vertical-align: top;
    }}
    th {{
      background: #0b1329;
      color: #94a3b8;
      font-weight: 600;
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    tr:last-child td {{ border-bottom: none; }}
    tr:hover td {{ background: rgba(255,255,255,0.02); }}
    .badge {{
      display: inline-block;
      padding: 0.2rem 0.6rem;
      border-radius: 9999px;
      font-size: 0.8rem;
      font-weight: 600;
      background: #334155;
      color: #e2e8f0;
    }}
    .badge.count {{
      background: #0369a1;
      color: #bae6fd;
    }}
    code {{ color: #38bdf8; font-size: 0.85rem; }}
    details.calc-dropdown summary {{
      cursor: pointer;
      user-select: none;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }}
    details.calc-dropdown[open] summary span:last-child {{
      color: #f43f5e;
    }}
    .calc-list::-webkit-scrollbar {{
      width: 6px;
    }}
    .calc-list::-webkit-scrollbar-thumb {{
      background: #334155;
      border-radius: 3px;
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <h1>👥 User Activity & Calculations Dashboard</h1>
        <p style="color:#94a3b8;margin:0.25rem 0 0;font-size:0.9rem;">Real-time Firestore user profiles & calculation history</p>
      </div>
      <div>
        <a href="/" class="btn">← Back to Calculator</a>
      </div>
    </header>

    <div class="metrics-section">
      <div class="metrics-group-title">🌐 Lifetime Summary</div>
      <div class="metrics-grid">
        <div class="metric-card">
          <span class="metric-label">Total Lifetime Users</span>
          <span class="metric-val">{lt['total_users']}</span>
        </div>
        <div class="metric-card">
          <span class="metric-label">Total Sessions (Logins)</span>
          <span class="metric-val">{lt['total_sessions']}</span>
        </div>
        <div class="metric-card">
          <span class="metric-label">Total Calculations</span>
          <span class="metric-val">{lt['total_calculations']}</span>
        </div>
      </div>

      <div class="metrics-group-title" style="color:#38bdf8;">⚡ Last 7 Days Activity</div>
      <div class="metrics-grid">
        <div class="metric-card recent">
          <span class="metric-label">Active Users (7d)</span>
          <span class="metric-val">{w7['active_users']}</span>
        </div>
        <div class="metric-card recent">
          <span class="metric-label">Sessions / Logins (7d)</span>
          <span class="metric-val">{w7['sessions']}</span>
        </div>
        <div class="metric-card recent">
          <span class="metric-label">Calculations (7d)</span>
          <span class="metric-val">{w7['calculations']}</span>
        </div>
      </div>
    </div>

    <div class="metrics-group-title">📋 User Details</div>
    <table>
      <thead>
        <tr>
          <th>User</th>
          <th>Email</th>
          <th style="text-align:center;">Logins</th>
          <th>Calculations History</th>
          <th>First Seen (UTC)</th>
          <th>Last Active (UTC)</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
  </div>
</body>
</html>"""
    return HTMLResponse(content=html)

@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Static files for web UI
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.api_route("/", methods=["GET", "HEAD"])
def serve_index():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Calculator API is running. Build static assets for UI."}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
