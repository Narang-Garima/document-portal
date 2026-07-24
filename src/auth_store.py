from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import smtplib
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

from logger import get_logger

log = get_logger(__name__)
BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("AUTH_DB_PATH", BASE_DIR / "data" / "auth.db"))
OTP_TTL_MINUTES = int(os.getenv("OTP_TTL_MINUTES", "10"))
OTP_MAX_ATTEMPTS = int(os.getenv("OTP_MAX_ATTEMPTS", "5"))


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _otp_hash(email: str, otp: str) -> str:
    secret = os.getenv("SESSION_SECRET", "development-only-change-me")
    payload = f"{email.lower()}:{otp}:{secret}".encode()
    return hashlib.sha256(payload).hexdigest()


def initialize_auth_store() -> None:
    with closing(_connect()) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                role TEXT NOT NULL DEFAULT 'user',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS otp_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL COLLATE NOCASE,
                otp_hash TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                consumed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_otp_email ON otp_codes(email, consumed, created_at);
            """
        )
        admin_email = os.getenv("ADMIN_EMAIL", "admin@local")
        connection.execute(
            "INSERT OR IGNORE INTO users(email, role, active, created_at) VALUES (?, 'admin', 1, ?)",
            (admin_email, _utcnow().isoformat()),
        )
        connection.commit()


def normalize_email(email: str) -> str:
    value = email.strip().lower()
    if value == "admin":
        return os.getenv("ADMIN_EMAIL", "admin@local").lower()
    return value


def get_user(email: str):
    normalized = normalize_email(email)
    with closing(_connect()) as connection:
        return connection.execute(
            "SELECT id, email, role, active, created_at FROM users WHERE email = ?",
            (normalized,),
        ).fetchone()


def list_users() -> list[dict]:
    with closing(_connect()) as connection:
        rows = connection.execute(
            "SELECT id, email, role, active, created_at FROM users ORDER BY created_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def add_user(email: str, role: str = "user") -> dict:
    normalized = normalize_email(email)
    if "@" not in normalized:
        raise ValueError("Enter a valid email address.")
    if role not in {"user", "admin"}:
        raise ValueError("Role must be 'user' or 'admin'.")
    with closing(_connect()) as connection:
        try:
            connection.execute(
                "INSERT INTO users(email, role, active, created_at) VALUES (?, ?, 1, ?)",
                (normalized, role, _utcnow().isoformat()),
            )
            connection.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError("That user already exists.") from exc
    return dict(get_user(normalized))


def set_user_active(email: str, active: bool) -> None:
    normalized = normalize_email(email)
    with closing(_connect()) as connection:
        connection.execute("UPDATE users SET active = ? WHERE email = ?", (1 if active else 0, normalized))
        connection.commit()


def _send_otp_email(email: str, otp: str) -> None:
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_from = os.getenv("SMTP_FROM", smtp_username or "documentportal@localhost")
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"

    if not smtp_host:
        if os.getenv("OTP_DEBUG", "true").lower() == "true":
            log.warning("OTP_DEBUG enabled. Login OTP for %s is %s", email, otp)
            return
        raise RuntimeError("SMTP is not configured. Set SMTP_HOST or enable OTP_DEBUG for local development.")

    message = EmailMessage()
    message["Subject"] = "Your DocumentPortal login code"
    message["From"] = smtp_from
    message["To"] = email
    message.set_content(
        f"Your DocumentPortal one-time login code is: {otp}\n\n"
        f"This code expires in {OTP_TTL_MINUTES} minutes."
    )

    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as client:
        if use_tls:
            client.starttls()
        if smtp_username:
            client.login(smtp_username, smtp_password or "")
        client.send_message(message)


def create_otp(email: str) -> str:
    normalized = normalize_email(email)
    user = get_user(normalized)
    if not user or not user["active"]:
        raise ValueError("This email is not authorized. Ask an administrator to add it.")

    otp = f"{secrets.randbelow(1_000_000):06d}"
    now = _utcnow()
    expires_at = now + timedelta(minutes=OTP_TTL_MINUTES)
    with closing(_connect()) as connection:
        connection.execute(
            "UPDATE otp_codes SET consumed = 1 WHERE email = ? AND consumed = 0",
            (normalized,),
        )
        connection.execute(
            "INSERT INTO otp_codes(email, otp_hash, expires_at, attempts, consumed, created_at) VALUES (?, ?, ?, 0, 0, ?)",
            (normalized, _otp_hash(normalized, otp), expires_at.isoformat(), now.isoformat()),
        )
        connection.commit()

    _send_otp_email(normalized, otp)
    return otp


def verify_otp(email: str, otp: str) -> dict | None:
    normalized = normalize_email(email)
    with closing(_connect()) as connection:
        row = connection.execute(
            "SELECT * FROM otp_codes WHERE email = ? AND consumed = 0 ORDER BY id DESC LIMIT 1",
            (normalized,),
        ).fetchone()
        if not row:
            return None
        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at < _utcnow() or row["attempts"] >= OTP_MAX_ATTEMPTS:
            connection.execute("UPDATE otp_codes SET consumed = 1 WHERE id = ?", (row["id"],))
            connection.commit()
            return None

        valid = hmac.compare_digest(row["otp_hash"], _otp_hash(normalized, otp.strip()))
        if valid:
            connection.execute("UPDATE otp_codes SET consumed = 1 WHERE id = ?", (row["id"],))
            connection.commit()
            user = get_user(normalized)
            return dict(user) if user and user["active"] else None

        connection.execute("UPDATE otp_codes SET attempts = attempts + 1 WHERE id = ?", (row["id"],))
        connection.commit()
        return None
