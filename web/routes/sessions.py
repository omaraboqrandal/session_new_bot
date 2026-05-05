"""
Sessions API routes — list, detail, logout, delete, export.
"""

import os
import asyncio
import zipfile
import tempfile
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

from web.auth import require_auth
import database.database as db
from utils.country_utils import (
    get_all_sessions, get_country_display, SESSIONS_DIR,
)
from config.config_manager import get_proxy, get_api_credentials
from workers.session_worker import create_client, get_last_otp

logger = logging.getLogger("web.sessions")
router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("")
async def list_sessions(_=Depends(require_auth)):
    """List all sessions grouped by country."""
    all_sessions = get_all_sessions()
    all_statuses = await db.get_all_statuses()
    all_contact = await db.get_all_contact_statuses()

    result = {}
    for folder, phones in all_sessions.items():
        flag, name = get_country_display(folder)
        result[folder] = {
            "flag": flag,
            "name": name,
            "phones": [
                {
                    "phone": p,
                    "spam_status": all_statuses.get(p, "Unknown"),
                    "contact_status": all_contact.get(p, "Unknown"),
                }
                for p in phones
            ],
        }
    return result


@router.get("/{phone}")
async def session_detail(phone: str, _=Depends(require_auth)):
    """Get details for a specific session."""
    all_sessions = get_all_sessions()
    folder = None
    for f, phones in all_sessions.items():
        if phone in phones:
            folder = f
            break
    if not folder:
        raise HTTPException(status_code=404, detail="Session not found")

    flag, name = get_country_display(folder)
    spam = await db.get_session_status(phone)
    contact = await db.get_contact_status(phone)

    return {
        "phone": phone,
        "country": name,
        "flag": flag,
        "folder": folder,
        "spam_status": spam,
        "contact_status": contact,
    }


class PhoneAction(BaseModel):
    phone: str


@router.post("/{phone}/logout")
async def logout_session(phone: str, _=Depends(require_auth)):
    """Log out a Telegram session."""
    session_file = _find_session_file(phone)
    if not session_file:
        raise HTTPException(status_code=404, detail="Session not found")

    api_id, api_hash = await get_api_credentials()
    proxy = await get_proxy()
    client = None

    try:
        client = create_client(session_file, api_id, api_hash, proxy)
        await client.connect()
        if await client.is_user_authorized():
            await client.log_out()
        await client.disconnect()
        await asyncio.sleep(0.5)

        # Delete local files
        for ext in [".session", ".session-journal"]:
            path = session_file + ext
            if os.path.exists(path):
                try:
                    os.remove(path)
                except PermissionError:
                    await asyncio.sleep(1)
                    try:
                        os.remove(path)
                    except Exception:
                        pass

        await db.delete_session_status(phone)
        await db.delete_contact_status(phone)
        _cleanup_empty_folder(session_file)
        await db.log_action(0, "web_logout", f"+{phone}")

        return {"status": "ok", "message": f"+{phone} logged out successfully"}

    except Exception as e:
        logger.error("Logout error for +%s: %s", phone, e)
        if client:
            try:
                await client.disconnect()
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Logout failed: {type(e).__name__}")


@router.delete("/{phone}")
async def delete_session(phone: str, _=Depends(require_auth)):
    """Delete a session file and DB status."""
    if not os.path.exists(SESSIONS_DIR):
        raise HTTPException(status_code=404, detail="Session not found")

    deleted = False
    for folder in os.listdir(SESSIONS_DIR):
        folder_path = os.path.join(SESSIONS_DIR, folder)
        if not os.path.isdir(folder_path):
            continue
        session_file = os.path.join(folder_path, f"{phone}.session")
        if os.path.exists(session_file):
            for path in [session_file, session_file + "-journal"]:
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except PermissionError:
                        await asyncio.sleep(1)
                        try:
                            os.remove(path)
                        except Exception:
                            pass
            deleted = True
            await db.delete_session_status(phone)
            await db.delete_contact_status(phone)
            # Remove folder if empty
            remaining = [f for f in os.listdir(folder_path) if f.endswith(".session")]
            if not remaining:
                try:
                    os.rmdir(folder_path)
                except OSError:
                    pass
            break

    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")

    await db.log_action(0, "web_delete", f"+{phone}")
    return {"status": "ok", "message": f"+{phone} deleted"}


@router.get("/export/all")
async def export_all_sessions(_=Depends(require_auth)):
    """Export all sessions as a ZIP file."""
    all_sessions = get_all_sessions()
    if not all_sessions:
        raise HTTPException(status_code=404, detail="No sessions to export")

    tmp_zip = os.path.join(tempfile.gettempdir(), "web_export_all.zip")
    total = 0
    try:
        with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for folder, phones in all_sessions.items():
                for phone in phones:
                    sf = os.path.join(SESSIONS_DIR, folder, f"{phone}.session")
                    if os.path.exists(sf):
                        zf.write(sf, f"{folder}/{phone}.session")
                        total += 1

        if total == 0:
            raise HTTPException(status_code=404, detail="No session files found")

        await db.log_action(0, "web_export", f"{total} sessions")
        return FileResponse(
            tmp_zip,
            media_type="application/zip",
            filename="sessions_export.zip",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Export error: %s", e)
        raise HTTPException(status_code=500, detail="Export failed")


@router.get("/{phone}/otp")
async def get_otp(phone: str, _=Depends(require_auth)):
    """Fetch last OTP code for a session."""
    session_file = _find_session_file(phone)
    if not session_file:
        raise HTTPException(status_code=404, detail="Session not found")

    api_id, api_hash = await get_api_credentials()
    proxy = await get_proxy()
    client = None

    try:
        client = create_client(session_file, api_id, api_hash, proxy)
        await client.connect()

        if not await client.is_user_authorized():
            await client.disconnect()
            raise HTTPException(status_code=400, detail="Session not authorized")

        found, message = await get_last_otp(client)
        await client.disconnect()

        return {"found": found, "message": message}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("OTP error for +%s: %s", phone, e)
        if client:
            try:
                await client.disconnect()
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"OTP fetch failed: {type(e).__name__}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_session_file(phone: str) -> str | None:
    """Find session file path (without .session extension) for a phone."""
    if not os.path.exists(SESSIONS_DIR):
        return None
    for folder in os.listdir(SESSIONS_DIR):
        folder_path = os.path.join(SESSIONS_DIR, folder)
        if not os.path.isdir(folder_path):
            continue
        candidate = os.path.join(folder_path, f"{phone}.session")
        if os.path.exists(candidate):
            return os.path.join(folder_path, phone)
    return None


def _cleanup_empty_folder(session_file: str) -> None:
    """Remove the parent folder if it's empty after a session is removed."""
    folder_path = os.path.dirname(session_file)
    if os.path.exists(folder_path):
        remaining = [f for f in os.listdir(folder_path) if f.endswith(".session")]
        if not remaining:
            try:
                os.rmdir(folder_path)
            except OSError:
                pass
