"""
Register handler — Phone registration flow with FSM.
"""
from utils.utils import smart_edit

import os
import io
import asyncio
import random
import string
import logging
import aiohttp
from PIL import Image
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from ui.states import RegState
from ui.keyboards import cancel_kb, back_menu_kb
from config.config_manager import get_proxy, get_api_credentials, get_profile_settings
from utils.country_utils import detect_country, get_session_dir, set_session_status, set_contact_status
from workers.session_worker import (
    create_client,
    check_spam,
    check_contact_limit,
    PhoneNumberInvalidError,
    PhoneNumberBannedError,
    FloodWaitError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    SessionPasswordNeededError,
)
from handlers.common import is_admin_async, is_write_admin_async

router = Router()
logger = logging.getLogger(__name__)

# Active Telethon clients: {user_id: {"client": ..., "phone": ..., "hash": ..., "timeout_task": ...}}
_active: dict[int, dict] = {}

async def cleanup_registration(uid: int, message: Message = None, state: FSMContext = None):
    """Disconnects the client and deletes the session files if active."""
    if uid in _active:
        reg = _active[uid]
        client = reg.get("client")
        
        if "timeout_task" in reg and not reg["timeout_task"].done():
            reg["timeout_task"].cancel()

        phone = reg.get("phone")
        country = reg.get("country")

        try:
            await client.disconnect()
        except Exception:
            pass
            
        if phone and country:
            session_dir = get_session_dir(country)
            session_path = os.path.join(session_dir, phone)
            for ext in ["", ".session", ".session-journal", ".session-shm", ".session-wal"]:
                p = session_path + ext
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass
        del _active[uid]

        if message and state:
            try:
                await message.answer("⏳ <b>Timeout!</b> Registration session closed and deleted.", parse_mode="HTML")
                await state.clear()
            except Exception:
                pass


RANDOMUSER_API = "https://randomuser.me/api/"


async def _fetch_random_user() -> dict | None:
    """Fetch one random user from randomuser.me API. Returns the result dict or None on failure."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(RANDOMUSER_API, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = data.get("results", [])
                    if results:
                        return results[0]
    except Exception as e:
        logger.warning(f"randomuser.me API failed: {e}")
    return None


async def _download_url_bytes(url: str) -> bytes | None:
    """Download bytes from a URL. Returns None on failure."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    return await resp.read()
    except Exception as e:
        logger.warning(f"Failed to download {url}: {e}")
    return None


def _upscale_photo(raw_bytes: bytes, min_size: int = 512) -> bytes:
    """
    Upscale image to at least min_size x min_size using Pillow (LANCZOS).
    Telegram requires photos >= ~10 KB and reasonable dimensions.
    Returns JPEG bytes.
    """
    img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
    w, h = img.size
    if w < min_size or h < min_size:
        scale = max(min_size / w, min_size / h)
        new_w = int(w * scale)
        new_h = int(h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=95)
    out.seek(0)
    return out.read()


# 50 bio templates using randomuser.me fields
_BIO_TEMPLATES = [
    lambda u: f"📍 {u['city']}, {u['country']}",
    lambda u: f"🌍 {u['country']} · {u['age']} y.o.",
    lambda u: f"✈️ From {u['city']} | {u['age']} years",
    lambda u: f"🏙️ {u['city']} | {u['country']}",
    lambda u: f"🎂 {u['age']} · {u['city']}",
    lambda u: f"📌 Based in {u['city']}",
    lambda u: f"🌐 {u['country']} | {u['age']} y.o.",
    lambda u: f"🏠 {u['city']}, {u['state']}",
    lambda u: f"👤 {u['age']} · {u['country']}",
    lambda u: f"🌆 {u['city']} · {u['state']}",
    lambda u: f"📍 {u['state']}, {u['country']}",
    lambda u: f"🗺️ {u['country']} · {u['city']}",
    lambda u: f"🎯 {u['city']} | {u['age']} yrs",
    lambda u: f"🌟 {u['age']} from {u['country']}",
    lambda u: f"☕ {u['city']} vibes · {u['age']}",
    lambda u: f"🏔️ {u['state']} · {u['country']}",
    lambda u: f"🌙 {u['age']} · {u['city']}, {u['country']}",
    lambda u: f"✨ {u['city']} | {u['country']}",
    lambda u: f"🎵 {u['age']} y.o. · {u['city']}",
    lambda u: f"📷 {u['city']} · {u['state']}",
    lambda u: f"💫 {u['country']} · {u['age']}",
    lambda u: f"🌊 {u['city']}, {u['country']} · {u['age']}",
    lambda u: f"🔥 {u['age']} | {u['city']}",
    lambda u: f"🎨 {u['city']} · {u['country']}",
    lambda u: f"⚡ {u['state']} · {u['age']} y.o.",
    lambda u: f"🌺 {u['country']} | {u['city']}",
    lambda u: f"🎸 {u['age']} from {u['city']}",
    lambda u: f"🏖️ {u['city']} · {u['age']}",
    lambda u: f"🎭 {u['state']}, {u['country']}",
    lambda u: f"🚀 {u['age']} · {u['country']}",
    lambda u: f"🌸 {u['city']} | {u['age']} years old",
    lambda u: f"🦋 {u['country']} · {u['city']}",
    lambda u: f"⭐ {u['age']} · {u['state']}",
    lambda u: f"🎯 {u['country']} | {u['city']}",
    lambda u: f"🌈 {u['city']}, {u['state']}",
    lambda u: f"🏄 {u['age']} · {u['city']}, {u['country']}",
    lambda u: f"🎪 {u['state']} · {u['age']}",
    lambda u: f"🦅 {u['country']} born · {u['age']}",
    lambda u: f"🌍 {u['city']} · {u['country']} · {u['age']}",
    lambda u: f"🎻 {u['age']} y.o. · {u['country']}",
    lambda u: f"🌵 {u['state']}, {u['country']}",
    lambda u: f"🏡 {u['city']} · {u['age']} yrs",
    lambda u: f"🎲 {u['age']} | {u['state']}",
    lambda u: f"🌾 From {u['state']}, {u['country']}",
    lambda u: f"🎬 {u['city']} | {u['age']}",
    lambda u: f"🌏 {u['country']} · {u['age']} y.o.",
    lambda u: f"🏋️ {u['age']} · {u['city']}",
    lambda u: f"🎓 {u['city']}, {u['country']}",
    lambda u: f"🌻 {u['age']} from {u['state']}",
    lambda u: f"💎 {u['city']} · {u['country']} · {u['age']}",
]


def _build_bio_from_user(u: dict) -> str:
    """Pick a random bio template and fill it with API data."""
    city    = u.get("location", {}).get("city", "")
    state   = u.get("location", {}).get("state", "")
    country = u.get("location", {}).get("country", "")
    age     = str(u.get("dob", {}).get("age", ""))

    # Only use templates that will produce non-empty output
    data = {"city": city, "state": state, "country": country, "age": age}
    # Shuffle templates and pick first one that doesn't crash / gives content
    templates = list(_BIO_TEMPLATES)
    random.shuffle(templates)
    for tmpl in templates:
        try:
            result = tmpl(data).strip()
            if result and len(result) <= 70:   # Telegram bio limit is 70 chars
                return result
        except Exception:
            continue
    return f"📍 {city}, {country}".strip(" ,") if city or country else ""


async def _apply_profile(client, bot: Bot, profile: dict) -> list[str]:
    """
    Apply profile auto-fill settings to a freshly registered account.
    All data (username, name, photo, bio) is generated from randomuser.me API.
    Returns a list of applied actions (for display in the success message).
    """
    applied = []

    # Fetch random user data once if any field is enabled
    need_api = (
        profile.get("auto_username")
        or profile.get("auto_name")
        or profile.get("auto_photo")
        or profile.get("auto_bio")
    )
    if not need_api:
        return applied

    random_user = await _fetch_random_user()
    if random_user:
        logger.info("randomuser.me data fetched successfully")
    else:
        logger.warning("randomuser.me unavailable — skipping profile apply")
        return applied

    # Extract common fields once
    first   = random_user.get("name", {}).get("first", "")
    last    = random_user.get("name", {}).get("last", "")
    age     = str(random_user.get("dob", {}).get("age", ""))

    try:
        # ── Username: first + last + age + 3 random digits ────────────────────
        if profile.get("auto_username"):
            rand_digits = "".join(random.choices(string.digits, k=3))
            # Build from first+last (ASCII-safe: keep alnum only)
            base = (first + last).lower()
            base = "".join(c for c in base if c.isalnum())
            if not base:
                base = "user"
            raw_username = f"{base}{age}{rand_digits}"
            # Telegram: 5–32 chars, letters/digits/underscore
            username = raw_username[:32]
            if len(username) < 5:
                username = username + rand_digits + "tg"
            try:
                from telethon.tl.functions.account import UpdateUsernameRequest
                await client(UpdateUsernameRequest(username=username))
                applied.append(f"📛 Username: @{username}")
            except Exception as e:
                logger.warning(f"Could not set username: {e}")

        # ── Name ──────────────────────────────────────────────────────────────
        if profile.get("auto_name"):
            if first:
                try:
                    from telethon.tl.functions.account import UpdateProfileRequest
                    await client(UpdateProfileRequest(first_name=first, last_name=last))
                    applied.append(f"👤 Name: {first} {last}".strip())
                except Exception as e:
                    logger.warning(f"Could not set name: {e}")

        # ── Bio (random template from API data) ────────────────────────────────
        if profile.get("auto_bio"):
            bio_text = _build_bio_from_user(random_user)
            if bio_text:
                try:
                    from telethon.tl.functions.account import UpdateProfileRequest
                    await client(UpdateProfileRequest(about=bio_text))
                    applied.append(f"📝 Bio: {bio_text}")
                except Exception as e:
                    logger.warning(f"Could not set bio: {e}")

        # ── Profile Photo (large, upscaled to meet Telegram minimum) ──────────
        if profile.get("auto_photo"):
            photo_url = random_user.get("picture", {}).get("large", "")
            if photo_url:
                photo_data = await _download_url_bytes(photo_url)
                if photo_data:
                    try:
                        # Upscale to at least 512x512 so Telegram accepts it
                        photo_data = _upscale_photo(photo_data, min_size=512)
                        buf = io.BytesIO(photo_data)
                        buf.name = "photo.jpg"
                        from telethon.tl.functions.photos import UploadProfilePhotoRequest
                        uploaded = await client.upload_file(buf)
                        await client(UploadProfilePhotoRequest(file=uploaded))
                        applied.append("🖼 Profile photo: set")
                    except Exception as e:
                        logger.warning(f"Could not set profile photo: {e}")
                else:
                    logger.warning("Photo download returned empty bytes")
            else:
                logger.warning("No large photo URL in randomuser.me response")

    except Exception as e:
        logger.error(f"_apply_profile error: {e}")

    return applied


# ─── Start Registration ─────────────────────────────────────────────────────

@router.callback_query(F.data == "reg")
async def cb_register(callback: CallbackQuery, state: FSMContext):
    if not await is_write_admin_async(callback.from_user.id):
        await callback.answer("🚫 Not authorized", show_alert=True)
        return

    await state.set_state(RegState.phone)
    text = (
        "📱 <b>Register New Number</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Send the phone number with country code.\n\n"
        "📝 Example: <code>+966512345678</code>"
    )
    await smart_edit(callback.message, text, reply_markup=cancel_kb(), parse_mode="HTML")
    await callback.answer()


# ─── Receive Phone ───────────────────────────────────────────────────────────

@router.message(RegState.phone)
async def on_phone(message: Message, state: FSMContext):
    if not await is_write_admin_async(message.from_user.id):
        return

    phone = message.text.strip().lstrip("+")
    if not phone.isdigit() or len(phone) < 7:
        await message.answer(
            "❌ Invalid phone number. Send digits with country code.\n"
            "Example: <code>+966512345678</code>",
            reply_markup=cancel_kb(),
            parse_mode="HTML",
        )
        return

    code, country_name, flag = detect_country(phone)
    api_id, api_hash = await get_api_credentials()
    proxy = await get_proxy()

    session_dir = get_session_dir(country_name)
    session_path = os.path.join(session_dir, phone)

    status_msg = await message.answer(
        f"📤 Connecting & sending code...\n\n"
        f"📱 Phone: <code>+{phone}</code>\n"
        f"{flag} Country: <b>{country_name}</b> (+{code})",
        parse_mode="HTML",
    )

    # Cleanup any previous client
    uid = message.from_user.id
    if uid in _active:
        try:
            await _active[uid]["client"].disconnect()
        except Exception:
            pass
        del _active[uid]

    try:
        client = create_client(session_path, api_id, api_hash, proxy,)
        await client.connect()

        # Check if already authorized
        if await client.is_user_authorized():
            me = await client.get_me()
            status_msg = await smart_edit(status_msg, f"🕵️ Checking account status...\n\n"
                f"📱 <code>+{me.phone}</code>",
                parse_mode="HTML",
            )
            spam_status = await check_spam(client)
            contact_status = await check_contact_limit(client)
            await set_session_status(me.phone, spam_status)
            await set_contact_status(me.phone, contact_status)

            await client.disconnect()
            await state.clear()
            status_msg = await smart_edit(status_msg, f"✅ <b>Already authorized!</b>\n\n"
                f"👤 Name: <b>{me.first_name or ''} {me.last_name or ''}</b>\n"
                f"📱 Phone: <code>+{me.phone}</code>\n"
                f"🆔 ID: <code>{me.id}</code>\n"
                f"{flag} Country: <b>{country_name}</b>\n"
                f"🛡️ Spam: <b>{spam_status}</b>\n"
                f"📇 Contact: <b>{contact_status}</b>\n\n"
                f"📁 Session saved!",
                reply_markup=back_menu_kb(),
                parse_mode="HTML",
            )
            return

        sent = await client.send_code_request("+" + phone)

        _active[uid] = {
            "client": client,
            "phone": phone,
            "hash": sent.phone_code_hash,
            "country": country_name,
            "flag": flag,
            "code": code,
        }

        async def _timeout():
            await asyncio.sleep(300)
            await cleanup_registration(uid, message, state)

        _active[uid]["timeout_task"] = asyncio.create_task(_timeout())

        await state.set_state(RegState.code)
        status_msg = await smart_edit(status_msg, f"✅ <b>Code sent!</b>\n\n"
            f"📱 Phone: <code>+{phone}</code>\n"
            f"{flag} Country: {country_name}\n\n"
            f"📥 Enter the verification code:",
            reply_markup=cancel_kb(),
            parse_mode="HTML",
        )

    except PhoneNumberInvalidError:
        status_msg = await smart_edit(status_msg, "❌ <b>Invalid phone number!</b>", reply_markup=back_menu_kb(), parse_mode="HTML")
        await state.clear()
    except PhoneNumberBannedError:
        status_msg = await smart_edit(status_msg, "🚫 <b>This number is banned from Telegram!</b>", reply_markup=back_menu_kb(), parse_mode="HTML")
        await state.clear()
    except FloodWaitError as e:
        status_msg = await smart_edit(status_msg, f"⏳ <b>Flood wait!</b> Try again in <b>{e.seconds}</b> seconds.",
            reply_markup=back_menu_kb(),
            parse_mode="HTML",
        )
        await state.clear()
    except Exception as e:
        logger.error(f"Registration error: {e}")
        status_msg = await smart_edit(status_msg, f"❌ <b>Error:</b> <code>{type(e).__name__}: {e}</code>",
            reply_markup=back_menu_kb(),
            parse_mode="HTML",
        )
        await state.clear()


# ─── Receive Code ────────────────────────────────────────────────────────────

@router.message(RegState.code)
async def on_code(message: Message, state: FSMContext):
    if not await is_write_admin_async(message.from_user.id):
        return

    uid = message.from_user.id
    if uid not in _active:
        await message.answer("❌ Session expired. Start over.", reply_markup=back_menu_kb())
        await state.clear()
        return

    reg = _active[uid]
    client = reg["client"]
    verification_code = message.text.strip().replace(" ", "").replace("-", "")

    try:
        await client.sign_in(
            phone="+" + reg["phone"],
            code=verification_code,
            phone_code_hash=reg["hash"],
        )

        # Success!
        me = await client.get_me()

        status_msg = await message.answer("🕵️ Checking account status...")

        # Apply profile auto-fill settings
        profile = await get_profile_settings()
        applied_profile = []
        if any([
            profile.get("auto_username"),
            profile.get("auto_name"),
            profile.get("auto_photo"),
            profile.get("auto_bio"),
        ]):
            status_msg = await smart_edit(status_msg, "🎨 Applying profile settings...")
            applied_profile = await _apply_profile(client, message.bot, profile)
            status_msg = await smart_edit(status_msg, "🕵️ Checking account status...")

        spam_status = await check_spam(client)
        contact_status = await check_contact_limit(client)
        await set_session_status(me.phone, spam_status)
        await set_contact_status(me.phone, contact_status)

        await client.disconnect()
        if "timeout_task" in _active[uid] and not _active[uid]["timeout_task"].done():
            _active[uid]["timeout_task"].cancel()
        del _active[uid]
        await state.clear()

        try:
            await status_msg.delete()
        except Exception:
            pass

        profile_line = ""
        if applied_profile:
            profile_line = "\n🎨 <b>Profile applied:</b>\n" + "\n".join(f"  • {a}" for a in applied_profile) + "\n"

        await message.answer(
            f"✅ <b>Successfully registered!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 Name: <b>{me.first_name or ''} {me.last_name or ''}</b>\n"
            f"📱 Phone: <code>+{me.phone}</code>\n"
            f"🆔 ID: <code>{me.id}</code>\n"
            f"📛 Username: @{me.username or '—'}\n"
            f"{reg['flag']} Country: <b>{reg['country']}</b>\n"
            f"🛡️ Spam: <b>{spam_status}</b>\n"
            f"📇 Contact: <b>{contact_status}</b>\n"
            f"{profile_line}\n"
            f"📁 Session saved!",
            reply_markup=back_menu_kb(),
            parse_mode="HTML",
        )

    except SessionPasswordNeededError:
        if "timeout_task" in _active[uid] and not _active[uid]["timeout_task"].done():
            _active[uid]["timeout_task"].cancel()

        async def _timeout():
            await asyncio.sleep(300)
            await cleanup_registration(uid, message, state)
            
        _active[uid]["timeout_task"] = asyncio.create_task(_timeout())

        await state.set_state(RegState.password)
        await message.answer(
            "🔐 <b>Two-factor authentication enabled!</b>\n\n"
            "🔑 Enter your 2FA password:",
            reply_markup=cancel_kb(),
            parse_mode="HTML",
        )

    except PhoneCodeInvalidError:
        await message.answer(
            "❌ <b>Invalid code!</b> Try again:",
            reply_markup=cancel_kb(),
            parse_mode="HTML",
        )

    except PhoneCodeExpiredError:
        # Auto re-request a new code instead of making user start over
        try:
            sent = await client.send_code_request("+" + reg["phone"])
            _active[uid]["hash"] = sent.phone_code_hash
            logger.info(f"Code expired for +{reg['phone']}, auto re-requested new code")
            
            if "timeout_task" in _active[uid] and not _active[uid]["timeout_task"].done():
                _active[uid]["timeout_task"].cancel()

            async def _timeout():
                await asyncio.sleep(300)
                await cleanup_registration(uid, message, state)
                
            _active[uid]["timeout_task"] = asyncio.create_task(_timeout())
            await message.answer(
                "⏰ <b>Code expired — new code sent!</b>\n\n"
                f"📱 Phone: <code>+{reg['phone']}</code>\n\n"
                "📥 Enter the new verification code:",
                reply_markup=cancel_kb(),
                parse_mode="HTML",
            )
        except Exception as resend_err:
            logger.error(f"Failed to resend code for +{reg['phone']}: {resend_err}")
            if uid in _active:
                try:
                    await _active[uid]["client"].disconnect()
                except Exception:
                    pass
                del _active[uid]
            await state.clear()
            await message.answer(
                f"⏰ <b>Code expired & resend failed!</b>\n\n"
                f"Error: <code>{resend_err}</code>\n\nPlease start over.",
                reply_markup=back_menu_kb(),
                parse_mode="HTML",
            )

    except Exception as e:
        logger.error(f"Sign-in error: {e}")
        await cleanup_registration(uid)
        await state.clear()
        await message.answer(
            f"❌ <b>Error:</b> <code>{type(e).__name__}: {e}</code>",
            reply_markup=back_menu_kb(),
            parse_mode="HTML",
        )


# ─── Receive 2FA Password ───────────────────────────────────────────────────

@router.message(RegState.password)
async def on_password(message: Message, state: FSMContext):
    if not await is_write_admin_async(message.from_user.id):
        return

    uid = message.from_user.id
    if uid not in _active:
        await message.answer("❌ Session expired. Start over.", reply_markup=back_menu_kb())
        await state.clear()
        return

    reg = _active[uid]
    client = reg["client"]
    password = message.text.strip()

    try:
        await client.sign_in(password=password)

        me = await client.get_me()

        status_msg = await message.answer("🕵️ Checking account status...")

        # Apply profile auto-fill settings
        profile = await get_profile_settings()
        applied_profile = []
        if any([
            profile.get("auto_username"),
            profile.get("auto_name"),
            profile.get("auto_photo"),
            profile.get("auto_bio"),
        ]):
            status_msg = await smart_edit(status_msg, "🎨 Applying profile settings...")
            applied_profile = await _apply_profile(client, message.bot, profile)
            status_msg = await smart_edit(status_msg, "🕵️ Checking account status...")

        spam_status = await check_spam(client)
        contact_status = await check_contact_limit(client)
        await set_session_status(me.phone, spam_status)
        await set_contact_status(me.phone, contact_status)

        await client.disconnect()
        if "timeout_task" in _active[uid] and not _active[uid]["timeout_task"].done():
            _active[uid]["timeout_task"].cancel()
        del _active[uid]
        await state.clear()

        # Delete the password and status message for cleanliness
        try:
            await message.delete()
            await status_msg.delete()
        except Exception:
            pass

        profile_line = ""
        if applied_profile:
            profile_line = "\n🎨 <b>Profile applied:</b>\n" + "\n".join(f"  • {a}" for a in applied_profile) + "\n"

        await message.answer(
            f"✅ <b>Successfully registered!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 Name: <b>{me.first_name or ''} {me.last_name or ''}</b>\n"
            f"📱 Phone: <code>+{me.phone}</code>\n"
            f"🆔 ID: <code>{me.id}</code>\n"
            f"📛 Username: @{me.username or '—'}\n"
            f"{reg['flag']} Country: <b>{reg['country']}</b>\n"
            f"🛡️ Spam: <b>{spam_status}</b>\n"
            f"📇 Contact: <b>{contact_status}</b>\n"
            f"{profile_line}\n"
            f"📁 Session saved!",
            reply_markup=back_menu_kb(),
            parse_mode="HTML",
        )

    except Exception as e:
        logger.error(f"2FA error: {e}")
        await cleanup_registration(uid)
        await state.clear()
        await message.answer(
            f"❌ <b>2FA Error:</b> <code>{type(e).__name__}: {e}</code>",
            reply_markup=back_menu_kb(),
            parse_mode="HTML",
        )
