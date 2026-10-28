#!/usr/bin/env python3
"""
Quick utility script to inspect and dump all data in Firestore calculatordb
(Equivalent to: SELECT * FROM calculatordb;)
"""
import sys
import os

# Auto-switch to virtual environment python if running under system python
VENV_PYTHON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venv", "bin", "python")
if os.path.exists(VENV_PYTHON) and sys.executable != VENV_PYTHON:
    os.execv(VENV_PYTHON, [VENV_PYTHON] + sys.argv)

import warnings
warnings.filterwarnings("ignore")

from datetime import datetime, timezone
from google.cloud import firestore

GCP_PROJECT = os.environ.get("GCP_PROJECT", "chess-analyzer-497918")
FIRESTORE_DATABASE = os.environ.get("FIRESTORE_DATABASE", "calculatordb")

def main():
    print("=" * 65)
    print(f"📊 DUMPING FIRESTORE: {GCP_PROJECT} / {FIRESTORE_DATABASE}")
    print("=" * 65)

    try:
        db = firestore.Client(project=GCP_PROJECT, database=FIRESTORE_DATABASE)
    except Exception as e:
        print(f"❌ Failed to connect to Firestore: {e}")
        return

    users_ref = db.collection("users")
    users = list(users_ref.stream())

    if not users:
        print("No users found in database.")
        return

    total_calcs = 0
    total_logins = 0

    print(f"\nFound {len(users)} registered user(s):\n")

    for idx, u in enumerate(users, 1):
        data = u.to_dict()
        email = u.id
        name = data.get("name", "Unknown")
        login_count = data.get("login_count", 1)
        calc_count = data.get("calculation_count", 0)
        first_seen = data.get("first_seen", "-")
        last_active = data.get("last_active", data.get("last_seen", "-"))

        total_logins += login_count
        total_calcs += calc_count

        print(f"[{idx}] 👤 {name} <{email}>")
        print(f"    • Logins: {login_count} | Calculations: {calc_count}")
        print(f"    • First Seen:  {first_seen}")
        print(f"    • Last Active: {last_active}")

        # Fetch subcollection calculations
        calcs = list(
            u.reference.collection("history")
            .order_by("created_at", direction=firestore.Query.DESCENDING)
            .limit(20)
            .stream()
        )

        if calcs:
            print(f"    • Recent Calculations ({len(calcs)}):")
            for c in calcs:
                cd = c.to_dict()
                expr = cd.get("expression", "")
                res = cd.get("result", "")
                ts = cd.get("timestamp", "")
                print(f"        👉  {expr:<15} = {res:<12} (at {ts})")
        else:
            print("    • Recent Calculations: (None)")
        print("-" * 65)

    print(f"\n📈 SUMMARY METRICS:")
    print(f"   • Total Users:        {len(users)}")
    print(f"   • Total Sessions:     {total_logins}")
    print(f"   • Total Calculations: {total_calcs}\n")

if __name__ == "__main__":
    main()
