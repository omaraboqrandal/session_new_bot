"""
Shared utilities for handlers — admin check, action logging.
Supports:
  - Primary admin from ADMIN_ID env (always trusted)
  - Additional admins stored in database (multi-admin)

IMPORTANT: Always use is_admin_async() in handlers.
           is_admin() is kept only as a fast-path for the primary admin
           and will NOT catch DB-only admins.
"""

import os
import database.database as db


def _get_primary_admin() -> int:
    """Get the primary admin ID from env. Returns 0 if not set."""
    raw = os.getenv("ADMIN_ID", "0")
    try:
        return int(raw)
    except (ValueError, TypeError):
        return 0


# Sync fast-path — ONLY checks primary admin from env
def is_admin(user_id: int) -> bool:
    """
    Sync check: allows primary admin (ADMIN_ID) and unrestricted mode (ADMIN_ID=0).
    ⚠️  Does NOT check DB admins — use is_admin_async() for full check.
    """
    primary = _get_primary_admin()
    return primary == 0 or user_id == primary


async def is_admin_async(user_id: int) -> bool:
    """
    Full async check: primary admin OR any admin registered in DB.
    Always use this in handlers for read access.
    """
    # Fast-path: primary admin from env
    primary = _get_primary_admin()
    if primary == 0 or user_id == primary:
        return True

    # Check DB admins (multi-admin support)
    try:
        return await db.is_admin_db(user_id)
    except Exception:
        # If DB is not ready yet, fall back to env only
        return False


async def is_write_admin_async(user_id: int) -> bool:
    """
    Write check: allows primary admin and DB admins EXCEPT 'readonly'.
    """
    primary = _get_primary_admin()
    if primary == 0 or user_id == primary:
        return True

    try:
        role = await db.get_admin_role(user_id)
        if role and role != "readonly":
            return True
        return False
    except Exception:
        return False


async def log_action(user_id: int, action: str, detail: str = "") -> None:
    """Log an admin action to the database."""
    try:
        await db.log_action(user_id, action, detail)
    except Exception:
        pass  # Never crash a handler because of logging
