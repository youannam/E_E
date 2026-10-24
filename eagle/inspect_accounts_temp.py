import sqlite3
from pathlib import Path

db = Path("eagle_eye.db")
if not db.exists():
    raise SystemExit("Database file not found in the current folder.")

con = sqlite3.connect(str(db))
con.row_factory = sqlite3.Row

for table in ("accounts", "monitored_users", "password_reset_requests"):
    exists = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    ).fetchone()
    if not exists:
        print(f"\n{table}: table not found")
        continue

    columns = [
        row["name"] for row in
        con.execute(f'PRAGMA table_info("{table}")')
    ]
    print(f"\n=== {table} ===")
    print("Columns:", ", ".join(columns))

    if table == "accounts":
        wanted = [
            "id", "username", "role", "is_active",
            "must_change_password", "job_role", "permissions", "email"
        ]
        selected = [c for c in wanted if c in columns]
        query = "SELECT " + ", ".join(f'"{c}"' for c in selected) + ' FROM accounts'
        for row in con.execute(query):
            data = dict(row)
            if "email" in data:
                data["email"] = "present" if data["email"] else "missing"
            print(data)

    elif table == "monitored_users":
        wanted = [
            "id", "username", "department", "job_role",
            "status", "is_synthetic", "job_permissions"
        ]
        selected = [c for c in wanted if c in columns]
        if selected:
            query = "SELECT " + ", ".join(f'"{c}"' for c in selected) + ' FROM monitored_users LIMIT 30'
            for row in con.execute(query):
                print(dict(row))

    else:
        wanted = ["id", "username", "status", "created_at", "reviewed_at"]
        selected = [c for c in wanted if c in columns]
        if selected:
            query = "SELECT " + ", ".join(f'"{c}"' for c in selected) + ' FROM password_reset_requests ORDER BY id DESC LIMIT 20'
            for row in con.execute(query):
                print(dict(row))

con.close()
