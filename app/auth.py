"""API-key auth + usage caps + rate limits. SQLite-backed, no external deps.

Tier caps per spec (SIX_WEEK_PLAN_2026-07 W2 #5):
  free   $0      100 req/day
  basic  $15/mo  5,000 req/day
  pro    $49/mo  50,000 req/day
  ultra  $199/mo unlimited
"""

from __future__ import annotations

import os
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass

DAILY_CAPS: dict[str, int | None] = {
    "free": 100,
    "basic": 5_000,
    "pro": 50_000,
    "ultra": None,  # unlimited
}

# Per-plan sustained request/min ceilings (burst control on top of daily caps).
PER_MINUTE_CAPS: dict[str, int] = {
    "free": 10,
    "basic": 60,
    "pro": 300,
    "ultra": 1_000,
}

_DB_LOCK = threading.Lock()


def _db_path() -> str:
    return os.environ.get("ROI_DB_PATH", "roi_usage.db")


def init_db(db_path: str | None = None) -> None:
    path = db_path or _db_path()
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS api_keys (
                key TEXT PRIMARY KEY,
                plan TEXT NOT NULL,
                label TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS usage_daily (
                key TEXT NOT NULL,
                day TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (key, day)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS usage_minute (
                key TEXT NOT NULL,
                minute INTEGER NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (key, minute)
            )
            """
        )
        conn.commit()


def create_key(plan: str, label: str = "", db_path: str | None = None) -> str:
    if plan not in DAILY_CAPS:
        raise ValueError(f"unknown plan: {plan}")
    key = "roi_" + secrets.token_hex(24)
    path = db_path or _db_path()
    with _DB_LOCK, sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO api_keys (key, plan, label, created_at) VALUES (?, ?, ?, ?)",
            (key, plan, label, time.time()),
        )
        conn.commit()
    return key


@dataclass(frozen=True)
class KeyInfo:
    key: str
    plan: str
    label: str


def lookup_key(key: str, db_path: str | None = None) -> KeyInfo | None:
    path = db_path or _db_path()
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT key, plan, label FROM api_keys WHERE key = ?", (key,)
        ).fetchone()
    return KeyInfo(*row) if row else None


@dataclass(frozen=True)
class QuotaState:
    plan: str
    used_today: int
    daily_cap: int | None
    retry_after_seconds: int
    limited: bool
    reason: str | None  # "daily" | "rate" | None


def consume(key: str, plan: str, db_path: str | None = None) -> QuotaState:
    """Record one request against the key's quotas. Idempotent-free: call once
    per counted request. Raises nothing; caller inspects `limited`."""
    path = db_path or _db_path()
    now = time.time()
    day = time.strftime("%Y-%m-%d", time.gmtime(now))
    minute = int(now // 60)

    with _DB_LOCK, sqlite3.connect(path) as conn:
        # Per-minute rate limit first (cheap rejection).
        row = conn.execute(
            "SELECT count FROM usage_minute WHERE key = ? AND minute = ?",
            (key, minute),
        ).fetchone()
        used_min = row[0] if row else 0
        if used_min >= PER_MINUTE_CAPS[plan]:
            return QuotaState(
                plan=plan,
                used_today=_today_count(conn, key, day),
                daily_cap=DAILY_CAPS[plan],
                retry_after_seconds=60 - int(now % 60),
                limited=True,
                reason="rate",
            )

        # Daily cap.
        used_today = _today_count(conn, key, day)
        cap = DAILY_CAPS[plan]
        if cap is not None and used_today >= cap:
            return QuotaState(
                plan=plan,
                used_today=used_today,
                daily_cap=cap,
                retry_after_seconds=seconds_until_utc_midnight(now),
                limited=True,
                reason="daily",
            )

        conn.execute(
            "INSERT INTO usage_minute (key, minute, count) VALUES (?, ?, 1) "
            "ON CONFLICT(key, minute) DO UPDATE SET count = count + 1",
            (key, minute),
        )
        conn.execute(
            "INSERT INTO usage_daily (key, day, count) VALUES (?, ?, 1) "
            "ON CONFLICT(key, day) DO UPDATE SET count = count + 1",
            (key, day),
        )
        conn.commit()

    return QuotaState(
        plan=plan,
        used_today=used_today + 1,
        daily_cap=cap,
        retry_after_seconds=0,
        limited=False,
        reason=None,
    )


def peek(key: str, plan: str, db_path: str | None = None) -> QuotaState:
    """Current quota state WITHOUT counting a request (for status endpoints)."""
    path = db_path or _db_path()
    day = time.strftime("%Y-%m-%d", time.gmtime(time.time()))
    with sqlite3.connect(path) as conn:
        used_today = _today_count(conn, key, day)
    return QuotaState(
        plan=plan,
        used_today=used_today,
        daily_cap=DAILY_CAPS[plan],
        retry_after_seconds=0,
        limited=False,
        reason=None,
    )


def _today_count(conn: sqlite3.Connection, key: str, day: str) -> int:
    row = conn.execute(
        "SELECT count FROM usage_daily WHERE key = ? AND day = ?", (key, day)
    ).fetchone()
    return row[0] if row else 0


def seconds_until_utc_midnight(now: float) -> int:
    day_start = now - (now % 86400)
    return int(day_start + 86400 - now)
