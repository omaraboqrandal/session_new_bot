"""
Admins API routes — list, add, remove admins.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from web.auth import require_auth
import database.database as db

logger = logging.getLogger("web.admins")
router = APIRouter(prefix="/api/admins", tags=["admins"])


class AdminCreate(BaseModel):
    user_id: int
    role: str = "admin"


@router.get("")
async def list_admins(_=Depends(require_auth)):
    """List all admins."""
    admins = await db.get_all_admins()
    return {"admins": admins}


@router.post("")
async def add_admin(data: AdminCreate, _=Depends(require_auth)):
    """Add a new admin."""
    if data.role not in ("superadmin", "admin", "readonly"):
        raise HTTPException(status_code=400, detail="Invalid role. Must be: superadmin, admin, readonly")

    await db.add_admin(data.user_id, data.role)
    await db.log_action(0, "web_add_admin", f"user_id={data.user_id} role={data.role}")
    logger.info("Admin added via web: %d (%s)", data.user_id, data.role)
    return {"status": "ok", "message": f"Admin {data.user_id} added with role {data.role}"}


@router.delete("/{user_id}")
async def remove_admin(user_id: int, _=Depends(require_auth)):
    """Remove an admin."""
    # Check if admin exists
    role = await db.get_admin_role(user_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Admin not found")

    await db.remove_admin(user_id)
    await db.log_action(0, "web_remove_admin", f"user_id={user_id}")
    logger.info("Admin removed via web: %d", user_id)
    return {"status": "ok", "message": f"Admin {user_id} removed"}
