"""Local reviewer accounts and expiring server-side sessions."""
import datetime
import hashlib
import hmac
import json
import os
import secrets
import threading
import time

ITERATIONS = 600000
SESSIONS = {}
FAILURES = {}
LOCK = threading.Lock()
SCHEMA = """CREATE TABLE IF NOT EXISTS users(
 username TEXT PRIMARY KEY, display_name TEXT NOT NULL, role TEXT NOT NULL,
 salt TEXT NOT NULL, password_hash TEXT NOT NULL, created_at TEXT NOT NULL
)"""


def provision(con, username, display_name, password, role="reviewer"):
    if not username or len(username) > 80 or not display_name:
        raise ValueError("Username and full name are required")
    if len(password) < 14:
        raise ValueError("Use a password of at least 14 characters")
    if role not in ("admin", "reviewer", "analyst"):
        raise ValueError("Unknown role")
    con.execute(SCHEMA)
    salt = secrets.token_hex(32)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    con.execute("INSERT INTO users VALUES(?,?,?,?,?,?)", (username, display_name, role, salt, digest,
                datetime.datetime.now(datetime.timezone.utc).isoformat()))
    con.commit()


def configured(con):
    con.execute(SCHEMA)
    return con.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0


def login(con, username, password, client):
    now = time.monotonic()
    with LOCK:
        previous = [t for t in FAILURES.get(client, []) if now - t < 900]
        if len(previous) >= 5:
            raise ValueError("Too many sign-in attempts. Try again in 15 minutes.")
        # Count attempts before hashing so parallel requests cannot bypass throttling.
        FAILURES[client] = previous + [now]
    con.execute(SCHEMA)
    row = con.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    salt = bytes.fromhex(row["salt"]) if row else bytes(32)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS).hex()
    if not row or not hmac.compare_digest(digest, row["password_hash"]):
        raise ValueError("Invalid username or password")
    token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    session = {"username": row["username"], "name": row["display_name"], "role": row["role"],
               "csrf": csrf, "expires": now + 8 * 3600}
    with LOCK:
        FAILURES.pop(client, None)
        for key in list(SESSIONS):
            if SESSIONS[key]["expires"] < now:
                SESSIONS.pop(key)
        SESSIONS[token] = session
    return token, session


def resolve(token):
    with LOCK:
        session = SESSIONS.get(token)
        if session and session["expires"] > time.monotonic():
            return session.copy()
        SESSIONS.pop(token, None)
    return None


def logout(token):
    with LOCK:
        SESSIONS.pop(token, None)
