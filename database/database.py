"""
Database — aiosqlite async layer.
Single file that owns all tables and provides clean async API.

Tables:
  config        — key/value store (replaces config.json)
  account_status  — phone → spam status (replaces account_status.json)
  contact_status  — phone → contact limit status (replaces contact_status.json)
  admins        — authorised admin Telegram IDs
  action_log    — audit log of every admin action
  setup         — (replaces setup.json)
"""

import asyncio
import json
import logging
import os
import time
from typing import Any

import aiosqlite

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH  = os.path.join(BASE_DIR, "bot.db")

logger = logging.getLogger("database")

# ── single shared connection (set during init_db) ─────────────────────────────
_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    """Return the open db connection (must call init_db first)."""
    global _db
    if _db is None:
        raise RuntimeError("Database not initialised — call init_db() first")
    return _db


# ══════════════════════════════════════════════════════════════════════════════
#  INIT
# ══════════════════════════════════════════════════════════════════════════════

async def init_db() -> None:
    """Open the database and create all tables (idempotent)."""
    global _db
    _db = await aiosqlite.connect(DB_PATH)
    _db.row_factory = aiosqlite.Row
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.execute("PRAGMA foreign_keys=ON")

    await _db.executescript("""
        CREATE TABLE IF NOT EXISTS config (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS account_status (
            phone  TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'Unknown',
            updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
        );

        CREATE TABLE IF NOT EXISTS contact_status (
            phone  TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'Unknown',
            updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
        );

        CREATE TABLE IF NOT EXISTS admins (
            user_id    INTEGER PRIMARY KEY,
            role       TEXT NOT NULL DEFAULT 'admin',
            added_at   INTEGER NOT NULL DEFAULT (strftime('%s','now'))
        );

        CREATE TABLE IF NOT EXISTS action_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            action     TEXT NOT NULL,
            detail     TEXT,
            ts         INTEGER NOT NULL DEFAULT (strftime('%s','now'))
        );

        CREATE TABLE IF NOT EXISTS setup (
            id           TEXT PRIMARY KEY,
            proxy        TEXT,
            password     TEXT,
            setup_type   TEXT,
            created_at   INTEGER NOT NULL DEFAULT (strftime('%s','now'))
        );

        CREATE TABLE IF NOT EXISTS scheduler (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS web_tokens (
            token       TEXT PRIMARY KEY,
            created_at  INTEGER NOT NULL,
            expires_at  INTEGER NOT NULL,
            used        INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS web_sessions (
            session_id  TEXT PRIMARY KEY,
            created_at  INTEGER NOT NULL,
            expires_at  INTEGER NOT NULL,
            user_agent  TEXT
        );
    """)
    await _db.commit()
    logger.info("✅ Database initialised at %s", DB_PATH)


async def close_db() -> None:
    global _db
    if _db:
        await _db.close()
        _db = None


# ══════════════════════════════════════════════════════════════════════════════
#  CONFIG  (replaces config.json)
# ══════════════════════════════════════════════════════════════════════════════

_CONFIG_DEFAULTS: dict[str, Any] = {
    "api_id":   2040,
    "api_hash": "b18441a1ff607e10a989891a5462e627",
    "proxy": {
        "enabled":  False,
        "type":     "socks5",
        "host":     "",
        "port":     0,
        "username": "",
        "password": "",
        "rdns":     True,
    },
    "profile": {
        "auto_username": False,
        "auto_name":     False,
        "auto_photo":    False,
        "auto_bio":      False,
    },
}


def _encode(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False)


def _decode(s: str) -> Any:
    return json.loads(s)


async def cfg_get(key: str) -> Any:
    db = await get_db()
    async with db.execute("SELECT value FROM config WHERE key=?", (key,)) as cur:
        row = await cur.fetchone()
    if row is None:
        return _CONFIG_DEFAULTS.get(key)
    return _decode(row["value"])


async def cfg_set(key: str, value: Any) -> None:
    db = await get_db()
    await db.execute(
        "INSERT INTO config(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, _encode(value)),
    )
    await db.commit()


# ── proxy ─────────────────────────────────────────────────────────────────────

async def get_proxy() -> dict:
    return await cfg_get("proxy") or _CONFIG_DEFAULTS["proxy"]


async def set_proxy(proxy: dict) -> None:
    await cfg_set("proxy", proxy)


# ── api credentials ────────────────────────────────────────────────────────────

async def get_api_credentials() -> tuple[int, str]:
    api_id   = await cfg_get("api_id")   or _CONFIG_DEFAULTS["api_id"]
    api_hash = await cfg_get("api_hash") or _CONFIG_DEFAULTS["api_hash"]
    return int(api_id), str(api_hash)


async def set_api_id(api_id: int) -> None:
    await cfg_set("api_id", api_id)


async def set_api_hash(api_hash: str) -> None:
    await cfg_set("api_hash", api_hash)


# ── profile settings ───────────────────────────────────────────────────────────

async def get_profile_settings() -> dict:
    return await cfg_get("profile") or _CONFIG_DEFAULTS["profile"]


async def set_profile_settings(profile: dict) -> None:
    await cfg_set("profile", profile)


# ══════════════════════════════════════════════════════════════════════════════
#  ACCOUNT STATUS  (replaces account_status.json)
# ══════════════════════════════════════════════════════════════════════════════

async def get_all_statuses() -> dict[str, str]:
    db = await get_db()
    async with db.execute("SELECT phone, status FROM account_status") as cur:
        rows = await cur.fetchall()
    return {r["phone"]: r["status"] for r in rows}


async def get_session_status(phone: str) -> str:
    db = await get_db()
    async with db.execute(
        "SELECT status FROM account_status WHERE phone=?", (phone,)
    ) as cur:
        row = await cur.fetchone()
    return row["status"] if row else "Unknown"


async def set_session_status(phone: str, status: str) -> None:
    db = await get_db()
    await db.execute(
        "INSERT INTO account_status(phone,status,updated_at) VALUES(?,?,?) "
        "ON CONFLICT(phone) DO UPDATE SET status=excluded.status, updated_at=excluded.updated_at",
        (phone, status, int(time.time())),
    )
    await db.commit()


async def bulk_set_session_status(records: list[tuple[str, str]]) -> None:
    """Insert/update many (phone, status) pairs at once."""
    db = await get_db()
    now = int(time.time())
    await db.executemany(
        "INSERT INTO account_status(phone,status,updated_at) VALUES(?,?,?) "
        "ON CONFLICT(phone) DO UPDATE SET status=excluded.status, updated_at=excluded.updated_at",
        [(p, s, now) for p, s in records],
    )
    await db.commit()


async def delete_session_status(phone: str) -> None:
    db = await get_db()
    await db.execute("DELETE FROM account_status WHERE phone=?", (phone,))
    await db.commit()


# ══════════════════════════════════════════════════════════════════════════════
#  CONTACT STATUS  (replaces contact_status.json)
# ══════════════════════════════════════════════════════════════════════════════

async def get_all_contact_statuses() -> dict[str, str]:
    db = await get_db()
    async with db.execute("SELECT phone, status FROM contact_status") as cur:
        rows = await cur.fetchall()
    return {r["phone"]: r["status"] for r in rows}


async def get_contact_status(phone: str) -> str:
    db = await get_db()
    async with db.execute(
        "SELECT status FROM contact_status WHERE phone=?", (phone,)
    ) as cur:
        row = await cur.fetchone()
    return row["status"] if row else "Unknown"


async def set_contact_status(phone: str, status: str) -> None:
    db = await get_db()
    await db.execute(
        "INSERT INTO contact_status(phone,status,updated_at) VALUES(?,?,?) "
        "ON CONFLICT(phone) DO UPDATE SET status=excluded.status, updated_at=excluded.updated_at",
        (phone, status, int(time.time())),
    )
    await db.commit()


async def bulk_set_contact_status(records: list[tuple[str, str]]) -> None:
    db = await get_db()
    now = int(time.time())
    await db.executemany(
        "INSERT INTO contact_status(phone,status,updated_at) VALUES(?,?,?) "
        "ON CONFLICT(phone) DO UPDATE SET status=excluded.status, updated_at=excluded.updated_at",
        [(p, s, now) for p, s in records],
    )
    await db.commit()


async def delete_contact_status(phone: str) -> None:
    db = await get_db()
    await db.execute("DELETE FROM contact_status WHERE phone=?", (phone,))
    await db.commit()


# ══════════════════════════════════════════════════════════════════════════════
#  ADMINS  (multi-admin support)
# ══════════════════════════════════════════════════════════════════════════════

async def get_all_admins() -> list[dict]:
    db = await get_db()
    async with db.execute("SELECT user_id, role, added_at FROM admins") as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_admin_ids() -> set[int]:
    db = await get_db()
    async with db.execute("SELECT user_id FROM admins") as cur:
        rows = await cur.fetchall()
    return {r["user_id"] for r in rows}


async def add_admin(user_id: int, role: str = "admin") -> None:
    db = await get_db()
    await db.execute(
        "INSERT INTO admins(user_id,role) VALUES(?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET role=excluded.role",
        (user_id, role),
    )
    await db.commit()


async def remove_admin(user_id: int) -> None:
    db = await get_db()
    await db.execute("DELETE FROM admins WHERE user_id=?", (user_id,))
    await db.commit()


async def is_admin_db(user_id: int) -> bool:
    db = await get_db()
    async with db.execute(
        "SELECT 1 FROM admins WHERE user_id=?", (user_id,)
    ) as cur:
        return await cur.fetchone() is not None

async def get_admin_role(user_id: int) -> str | None:
    db = await get_db()
    async with db.execute(
        "SELECT role FROM admins WHERE user_id=?", (user_id,)
    ) as cur:
        row = await cur.fetchone()
        return row["role"] if row else None


# ══════════════════════════════════════════════════════════════════════════════
#  ACTION LOG
# ══════════════════════════════════════════════════════════════════════════════

async def log_action(user_id: int, action: str, detail: str = "") -> None:
    db = await get_db()
    await db.execute(
        "INSERT INTO action_log(user_id,action,detail,ts) VALUES(?,?,?,?)",
        (user_id, action, detail, int(time.time())),
    )
    await db.commit()


async def get_recent_logs(limit: int = 50) -> list[dict]:
    db = await get_db()
    async with db.execute(
        "SELECT user_id, action, detail, ts FROM action_log ORDER BY ts DESC LIMIT ?",
        (limit,),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════════════════════
#  SCHEDULER SETTINGS
# ══════════════════════════════════════════════════════════════════════════════

async def sched_get(key: str, default: Any = None) -> Any:
    db = await get_db()
    async with db.execute("SELECT value FROM scheduler WHERE key=?", (key,)) as cur:
        row = await cur.fetchone()
    if row is None:
        return default
    return _decode(row["value"])


async def sched_set(key: str, value: Any) -> None:
    db = await get_db()
    await db.execute(
        "INSERT INTO scheduler(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, _encode(value)),
    )
    await db.commit()


# ══════════════════════════════════════════════════════════════════════════════
#  SETUP  (replaces setup.json)
# ══════════════════════════════════════════════════════════════════════════════

async def get_all_setups() -> dict:
    db = await get_db()
    async with db.execute("SELECT id, proxy, password, setup_type FROM setup") as cur:
        rows = await cur.fetchall()
    return {r["id"]: {"proxy": r["proxy"], "password": r["password"], "setup_type": r["setup_type"]} for r in rows}


async def save_setup(setup_id: str, proxy: str, password: str, setup_type: str) -> None:
    db = await get_db()
    await db.execute(
        "INSERT INTO setup(id,proxy,password,setup_type) VALUES(?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET proxy=excluded.proxy, password=excluded.password, setup_type=excluded.setup_type",
        (setup_id, proxy, password, setup_type),
    )
    await db.commit()


async def delete_setup(setup_id: str) -> None:
    db = await get_db()
    await db.execute("DELETE FROM setup WHERE id=?", (setup_id,))
    await db.commit()


# ══════════════════════════════════════════════════════════════════════════════
#  WEB TOKENS  (one-time login tokens for web panel)
# ══════════════════════════════════════════════════════════════════════════════

async def create_web_token(token: str, expires_at: int) -> None:
    db = await get_db()
    await db.execute(
        "INSERT INTO web_tokens(token, created_at, expires_at, used) VALUES(?, ?, ?, 0)",
        (token, int(time.time()), expires_at),
    )
    await db.commit()


async def get_web_token(token: str) -> dict | None:
    db = await get_db()
    async with db.execute(
        "SELECT token, created_at, expires_at, used FROM web_tokens WHERE token=?", (token,)
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def mark_token_used(token: str) -> None:
    db = await get_db()
    await db.execute("UPDATE web_tokens SET used=1 WHERE token=?", (token,))
    await db.commit()


async def cleanup_expired_tokens() -> None:
    db = await get_db()
    now = int(time.time())
    await db.execute("DELETE FROM web_tokens WHERE expires_at < ? OR used = 1", (now,))
    await db.commit()


# ══════════════════════════════════════════════════════════════════════════════
#  WEB SESSIONS  (browser session cookies for web panel)
# ══════════════════════════════════════════════════════════════════════════════

async def create_web_session(session_id: str, expires_at: int, user_agent: str) -> None:
    db = await get_db()
    await db.execute(
        "INSERT INTO web_sessions(session_id, created_at, expires_at, user_agent) VALUES(?, ?, ?, ?)",
        (session_id, int(time.time()), expires_at, user_agent),
    )
    await db.commit()


async def get_web_session(session_id: str) -> dict | None:
    db = await get_db()
    async with db.execute(
        "SELECT session_id, created_at, expires_at, user_agent FROM web_sessions WHERE session_id=?",
        (session_id,),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def delete_web_session(session_id: str) -> None:
    db = await get_db()
    await db.execute("DELETE FROM web_sessions WHERE session_id=?", (session_id,))
    await db.commit()


async def cleanup_expired_web_sessions() -> None:
    db = await get_db()
    now = int(time.time())
    await db.execute("DELETE FROM web_sessions WHERE expires_at < ?", (now,))
    await db.commit()
