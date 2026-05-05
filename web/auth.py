"""
Web Panel Authentication — one-time token + session cookie system.
"""

import secrets
import time
import logging

from fastapi import Request, HTTPException

import database.database as db

logger = logging.getLogger("web.auth")

SESSION_COOKIE = "panel_session"
SESSION_DURATION = 86400  # 24 hours


async def validate_token_and_login(token: str, request: Request) -> str:
    """Validate one-time token, create session, return session_id."""
    record = await db.get_web_token(token)
    now = int(time.time())

    if not record:
        raise HTTPException(status_code=403, detail="Invalid token")
    if record["used"]:
        raise HTTPException(status_code=403, detail="Token already used")
    if record["expires_at"] < now:
        raise HTTPException(status_code=403, detail="Token expired")

    # Mark as used immediately
    await db.mark_token_used(token)

    # Create browser session
    session_id = secrets.token_urlsafe(32)
    user_agent = request.headers.get("user-agent", "")
    await db.create_web_session(session_id, now + SESSION_DURATION, user_agent)
    logger.info("New web session created from %s", request.client.host if request.client else "unknown")
    return session_id


async def require_auth(request: Request) -> bool:
    """Check if request has a valid session cookie. Raises 401 if not."""
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    record = await db.get_web_session(session_id)
    now = int(time.time())
    if not record or record["expires_at"] < now:
        raise HTTPException(status_code=401, detail="Session expired")
    return True
