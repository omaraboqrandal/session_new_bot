"""
Panel Handler — Generates one-time login tokens for the web panel.
"""

import os
import secrets
import time
import logging

import aiohttp
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from utils.utils import smart_edit
import database.database as db
from handlers.common import is_admin_async

router = Router()
logger = logging.getLogger(__name__)

TOKEN_EXPIRY = 600  # 10 minutes
PANEL_PORT = int(os.getenv("PANEL_PORT", "8080"))


async def _get_public_ip() -> str:
    """Fetch server's public IP from ipify API."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.ipify.org?format=json",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as r:
                data = await r.json()
                return data.get("ip", "Unknown")
    except Exception:
        return "Unknown"


def _panel_kb(has_token: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🔑 Generate New Token", callback_data="panel_gen_token")],
    ]
    if has_token:
        rows.insert(0, [InlineKeyboardButton(text="🔄 Refresh Info", callback_data="panel")])
    rows.append([InlineKeyboardButton(text="🔙 Back", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "panel")
async def cb_panel(callback: CallbackQuery):
    if not await is_admin_async(callback.from_user.id):
        await callback.answer("🚫", show_alert=True)
        return
    await callback.answer()

    public_ip = await _get_public_ip()
    panel_url = f"http://{public_ip}:{PANEL_PORT}"

    text = (
        "🌐 <b>Web Panel</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🖥 Server IP: <code>{public_ip}</code>\n"
        f"🔗 Panel URL: <code>{panel_url}</code>\n\n"
        "🔑 Generate a one-time login token below.\n"
        "⏱ Tokens expire after <b>10 minutes</b> and can only be used <b>once</b>.\n\n"
        "🔒 Do not share the token with anyone!"
    )
    await smart_edit(callback.message, text, reply_markup=_panel_kb(), parse_mode="HTML")


@router.callback_query(F.data == "panel_gen_token")
async def cb_gen_token(callback: CallbackQuery):
    if not await is_admin_async(callback.from_user.id):
        await callback.answer("🚫", show_alert=True)
        return
    await callback.answer()

    token = secrets.token_urlsafe(32)
    now = int(time.time())
    expires_at = now + TOKEN_EXPIRY

    await db.create_web_token(token, expires_at)

    public_ip = await _get_public_ip()
    panel_url = f"http://{public_ip}:{PANEL_PORT}"
    login_url = f"{panel_url}/login?token={token}"

    text = (
        "✅ <b>Token Generated!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔗 Login URL:\n<code>{login_url}</code>\n\n"
        "⏱ Expires in: <b>10 minutes</b>\n"
        "🔑 One-time use only — link expires after first login\n\n"
        "🔒 <b>Keep this link private!</b>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Open Panel", url=login_url)],
        [InlineKeyboardButton(text="🔑 Generate New Token", callback_data="panel_gen_token")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="panel")],
    ])
    await smart_edit(callback.message, text, reply_markup=kb, parse_mode="HTML")
