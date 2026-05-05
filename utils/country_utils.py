"""
Country Utilities — Detect country from phone number using countries.json.
Status functions now delegate to database.py (async).
"""

import os

import database.database as db
from .countries_data import COUNTRIES

BASE_DIR       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SESSIONS_DIR   = os.path.join(BASE_DIR, "sessions")

def load_countries() -> dict:
    """Return static countries dict from memory."""
    return COUNTRIES


def detect_country(phone: str) -> tuple[str, str, str]:
    countries    = load_countries()
    clean        = phone.lstrip("+").strip()
    sorted_codes = sorted(countries.keys(), key=len, reverse=True)
    for code in sorted_codes:
        if clean.startswith(code):
            info = countries[code]
            return code, info["name"], info["flag"]
    return "0", "Unknown", "🏳️"


def get_session_dir(country_name: str) -> str:
    safe = country_name.replace(" ", "_").replace("/", "_")
    path = os.path.join(SESSIONS_DIR, safe)
    os.makedirs(path, exist_ok=True)
    return path


def get_all_sessions() -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    if not os.path.exists(SESSIONS_DIR):
        return result
    for folder in sorted(os.listdir(SESSIONS_DIR)):
        folder_path = os.path.join(SESSIONS_DIR, folder)
        if not os.path.isdir(folder_path):
            continue
        sessions = [
            f.replace(".session", "")
            for f in sorted(os.listdir(folder_path))
            if f.endswith(".session")
        ]
        if sessions:
            result[folder] = sessions
    return result


def get_country_display(folder_name: str) -> tuple[str, str]:
    countries = load_countries()
    display   = folder_name.replace("_", " ")
    for _, info in countries.items():
        if info["name"].replace(" ", "_") == folder_name:
            return info["flag"], display
    return "🏳️", display


def get_total_stats() -> tuple[int, int]:
    all_sess = get_all_sessions()
    total    = sum(len(v) for v in all_sess.values())
    return total, len(all_sess)


# --- Account Status - async (DB) ---

async def get_all_statuses() -> dict[str, str]:
    return await db.get_all_statuses()

async def get_session_status(phone: str) -> str:
    return await db.get_session_status(phone)

async def set_session_status(phone: str, status: str) -> None:
    await db.set_session_status(phone, status)


# --- Contact Status - async (DB) ---

async def get_all_contact_statuses() -> dict[str, str]:
    return await db.get_all_contact_statuses()

async def get_contact_status(phone: str) -> str:
    return await db.get_contact_status(phone)

async def set_contact_status(phone: str, status: str) -> None:
    await db.set_contact_status(phone, status)
