"""
Check Handler — Spam check, Contact limit check, Session validity check.
Supports checking sessions from stored countries or from uploaded ZIP files.
"""
from utils.utils import smart_edit

import os
import zipfile
import tempfile
import asyncio
import logging
import shutil
import time
import database.database as db

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, FSInputFile
from aiogram.fsm.context import FSMContext

from ui.keyboards import (
    check_menu_kb,
    check_countries_list_kb,
    back_to_check_kb,
    back_menu_kb,
    cancel_kb,
)
from utils.country_utils import (
    get_all_sessions,
    get_country_display,
    SESSIONS_DIR,
)
from config.config_manager import get_proxy, get_api_credentials
from workers.session_worker import create_client, check_spam, check_contact_limit, check_session_alive
from handlers.common import is_admin_async, is_write_admin_async
from ui.states import CheckState

router = Router()
logger = logging.getLogger(__name__)


# ─── Check Menu ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "chk")
async def cb_check_menu(callback: CallbackQuery, state: FSMContext):
    if not await is_write_admin_async(callback.from_user.id):
        await callback.answer("🚫", show_alert=True)
        return

    await state.clear()
    text = (
        "🔍 <b>Check Sessions</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Choose a check type:"
    )
    await smart_edit(callback.message, text, reply_markup=check_menu_kb(), parse_mode="HTML")
    await callback.answer()


# ─── Check Type Selected → Show Countries ────────────────────────────────────

@router.callback_query(F.data.startswith("chk_type:"))
async def cb_check_type(callback: CallbackQuery):
    if not await is_write_admin_async(callback.from_user.id):
        await callback.answer("🚫", show_alert=True)
        return

    check_type = callback.data.split(":")[1]
    await _show_check_countries(callback, check_type, page=0)


@router.callback_query(F.data.startswith("chkl:"))
async def cb_check_countries_page(callback: CallbackQuery):
    if not await is_write_admin_async(callback.from_user.id):
        await callback.answer("🚫", show_alert=True)
        return

    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer("❌ Invalid data", show_alert=True)
        return

    check_type = parts[1]
    page = int(parts[2])
    await _show_check_countries(callback, check_type, page)


async def _show_check_countries(callback: CallbackQuery, check_type: str, page: int):
    """Show paginated country list for a check type."""
    all_sessions = get_all_sessions()

    if not all_sessions:
        await smart_edit(callback.message, "📭 <b>No sessions found.</b>\n\nRegister or import sessions first!",
            reply_markup=back_to_check_kb(),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    display = {}
    for folder, phones in all_sessions.items():
        flag, name = get_country_display(folder)
        display[folder] = (flag, name, len(phones))

    type_labels = {
        "spam": "🚫 Spam Check",
        "contact": "📇 Contact Limit Check",
        "alive": "✅ Session Validity Check",
    }
    label = type_labels.get(check_type, "Check")

    text = (
        f"🔍 <b>{label}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Select a country to check, or upload a ZIP:"
    )
    await smart_edit(callback.message, text,
        reply_markup=check_countries_list_kb(display, check_type, page),
        parse_mode="HTML",
    )
    await callback.answer()


# ─── Upload ZIP for Check ────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("chk_zip:"))
async def cb_check_upload_zip(callback: CallbackQuery, state: FSMContext):
    if not await is_write_admin_async(callback.from_user.id):
        await callback.answer("🚫", show_alert=True)
        return

    check_type = callback.data.split(":")[1]
    await state.set_state(CheckState.waiting_for_zip)
    await state.update_data(check_type=check_type)

    type_labels = {
        "spam": "🚫 Spam Check",
        "contact": "📇 Contact Limit Check",
        "alive": "✅ Session Validity Check",
    }
    label = type_labels.get(check_type, "Check")

    text = (
        f"📤 <b>Upload ZIP — {label}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Send me a <b>.zip</b> file containing <code>.session</code> files.\n\n"
        "⚠️ These sessions will <b>NOT</b> be saved to storage.\n"
        "They will only be checked and results sent back."
    )
    await smart_edit(callback.message, text, reply_markup=cancel_kb(), parse_mode="HTML")
    await callback.answer()


@router.message(CheckState.waiting_for_zip, F.document)
async def msg_check_zip_received(message: Message, state: FSMContext):
    if not await is_write_admin_async(message.from_user.id):
        return

    doc = message.document
    if not doc.file_name.endswith(".zip"):
        await message.answer("❌ Please send a <code>.zip</code> file.", reply_markup=cancel_kb(), parse_mode="HTML")
        return

    data = await state.get_data()
    check_type = data.get("check_type", "alive")
    await state.clear()

    status_msg = await message.answer("⏳ <b>Downloading and extracting ZIP...</b>", parse_mode="HTML")

    bot = message.bot
    file_info = await bot.get_file(doc.file_id)
    downloaded_file = await bot.download_file(file_info.file_path)

    # Create temp directory for extracted sessions
    tmp_dir = tempfile.mkdtemp(prefix="chk_zip_")

    try:
        # Extract session files
        session_files = []
        with zipfile.ZipFile(downloaded_file, "r") as zf:
            all_files = zf.namelist()
            for f in all_files:
                if f.endswith(".session") and "__MACOSX" not in f:
                    # Clean the filename
                    basename = os.path.basename(f)
                    clean = _clean_phone(basename)
                    if clean and clean.isdigit():
                        target = os.path.join(tmp_dir, f"{clean}.session")
                        file_data = zf.read(f)
                        with open(target, "wb") as out:
                            out.write(file_data)
                        session_files.append(clean)

        if not session_files:
            status_msg = await smart_edit(status_msg, "📭 <b>No valid .session files found in ZIP!</b>",
                reply_markup=back_to_check_kb(), parse_mode="HTML",
            )
            return

        status_msg = await smart_edit(status_msg, f"⏳ <b>Checking {len(session_files)} sessions...</b>\n\n"
            f"⏳ Processing <b>0/{len(session_files)}</b>...",
            parse_mode="HTML",
        )

        # Run checks
        results = await _run_checks(
            check_type, session_files, tmp_dir,
            status_msg, message, is_zip=True
        )

        # Send results
        await _send_results(check_type, results, tmp_dir, message, status_msg)

    except Exception as e:
        logger.error(f"Check ZIP error: {e}")
        status_msg = await smart_edit(status_msg, f"❌ <b>Check failed:</b> <code>{e}</code>",
            reply_markup=back_to_check_kb(), parse_mode="HTML",
        )
    finally:
        # Cleanup temp directory - do NOT save to storage
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ─── Check Country Sessions ─────────────────────────────────────────────────

@router.callback_query(F.data.startswith("chkc:"))
async def cb_check_country(callback: CallbackQuery):
    if not await is_write_admin_async(callback.from_user.id):
        await callback.answer("🚫", show_alert=True)
        return

    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer("❌ Invalid data", show_alert=True)
        return

    check_type = parts[1]
    folder = ":".join(parts[2:])
    all_sessions = get_all_sessions()

    if folder not in all_sessions:
        await callback.answer("❌ Country not found", show_alert=True)
        return

    phones = all_sessions[folder]
    flag, name = get_country_display(folder)
    folder_path = os.path.join(SESSIONS_DIR, folder)

    type_labels = {
        "spam": "🚫 Spam Check",
        "contact": "📇 Contact Limit Check",
        "alive": "✅ Session Validity Check",
    }
    label = type_labels.get(check_type, "Check")

    await smart_edit(callback.message, f"⏳ <b>{label} — {flag} {name}</b>\n\n"
        f"⏳ Processing <b>0/{len(phones)}</b>...",
        parse_mode="HTML",
    )
    await callback.answer()

    # Run checks
    results = await _run_checks(
        check_type, phones, folder_path,
        callback.message, callback.message, is_zip=False
    )

    # Send results
    await _send_results(check_type, results, folder_path, callback.message, callback.message)


# ─── Core Check Logic ────────────────────────────────────────────────────────

def _clean_phone(filename: str) -> str:
    """Extract clean phone from filename."""
    name = os.path.basename(filename)
    if name.endswith(".session"):
        name = name[:-8]
    return name.replace("+", "").replace(" ", "").replace("-", "").strip()


async def _run_checks(
    check_type: str,
    phones: list[str],
    sessions_dir: str,
    status_msg,
    context_msg,
    is_zip: bool = False,
) -> dict[str, list[str]]:
    """
    Run checks on a list of phones.
    Returns dict mapping status -> list of phones.
    """
    api_id, api_hash = await get_api_credentials()
    proxy = await get_proxy()
    total = len(phones)

    # Initialize results based on check type
    if check_type == "spam":
        results = {"Spam": [], "Free": [], "New": [], "Frozen": [], "Die": [], "Error": []}
    elif check_type == "contact":
        results = {"NoLimit": [], "Limited": [], "Frozen": [], "Die": [], "Error": []}
    else:  # alive
        results = {"Live": [], "Frozen": [], "Die": []}

    sem = asyncio.Semaphore(15)
    processed = 0
    last_update = time.time()

    async def _process_phone(phone: str):
        nonlocal processed, last_update
        session_path = os.path.join(sessions_dir, phone)

        async with sem:
            try:
                client = create_client(session_path, api_id, api_hash, proxy)
                await client.connect()

                if not await client.is_user_authorized():
                    await client.disconnect()
                    results["Die"].append(phone)
                    if not is_zip:
                        await db.set_session_status(phone, "BANNED")
                    logger.info(f"Check [{check_type}] +{phone}: Die")
                else:
                    if check_type == "spam":
                        status = await check_spam(client)
                        # Map status to our categories
                        if status == "SPAM":
                            results["Spam"].append(phone)
                        elif status == "FREE":
                            results["Free"].append(phone)
                        elif status == "NEW_REGISTERED":
                            results["New"].append(phone)
                        elif status == "BANNED":
                            results["Die"].append(phone)
                        else:
                            results["Error"].append(phone)
                            
                        if not is_zip and status not in ("Error", "Unknown"):
                            await db.set_session_status(phone, status)
                        await client.disconnect()

                    elif check_type == "contact":
                        status = await check_contact_limit(client)
                        if status == "NoLimit":
                            results["NoLimit"].append(phone)
                        elif status == "Limited":
                            results["Limited"].append(phone)
                        else:
                            results["Error"].append(phone)
                            
                        if not is_zip and status not in ("Error", "UNKNOWN"):
                            await db.set_contact_status(phone, status)
                        await client.disconnect()

                    else:  # alive
                        results["Live"].append(phone)
                        if not is_zip:
                            # if it's alive, we can mark it FREE or keep its old status, but typically 'alive' check doesn't update spam status.
                            # We can just update it to Alive if it was banned, but since we don't have an "Alive" status, we just leave it.
                            pass
                        await client.disconnect()

                    logger.info(f"Check [{check_type}] +{phone}: done")

            except Exception as e:
                logger.error(f"Check [{check_type}] +{phone} error: {e}")
                if check_type in ("spam", "contact"):
                    results["Frozen"].append(phone)
                else:
                    results["Frozen"].append(phone)

            processed += 1

            # Update progress every 2 seconds or at the end
            now = time.time()
            if now - last_update > 2.0 or processed == total:
                last_update = now
                try:
                    progress_lines = [f"⏳ Processing <b>{processed}/{total}</b>..."]
                    for key, vals in results.items():
                        if vals:
                            progress_lines.append(f"  {key}: {len(vals)}")

                    status_msg = await smart_edit(status_msg, f"⏳ <b>Checking...</b>\n\n" + "\n".join(progress_lines),
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

    tasks = [_process_phone(phone) for phone in phones]
    if tasks:
        await asyncio.gather(*tasks)

    return results


async def _send_results(
    check_type: str,
    results: dict[str, list[str]],
    sessions_dir: str,
    context_msg,
    status_msg,
):
    """Send formatted results and ZIP files grouped by status."""
    total = sum(len(v) for v in results.values())

    # Build results text
    if check_type == "spam":
        title = "✅ Completed limit check!"
        lines = [
            f"🚫 Spam: {len(results.get('Spam', []))}",
            f"✅ Free: {len(results.get('Free', []))}",
            f"🆕 New: {len(results.get('New', []))}",
            f"🧊 Frozen: {len(results.get('Frozen', []))}",
            f"❌ Die: {len(results.get('Die', []))}",
            f"⚠️ Error: {len(results.get('Error', []))}",
        ]
    elif check_type == "contact":
        title = "✅ Completed contact limit check!"
        lines = [
            f"✅ NoLimit: {len(results.get('NoLimit', []))}",
            f"⚠️ Limited: {len(results.get('Limited', []))}",
            f"🧊 Frozen: {len(results.get('Frozen', []))}",
            f"❌ Die: {len(results.get('Die', []))}",
            f"⚠️ Error: {len(results.get('Error', []))}",
        ]
    else:  # alive
        title = "✅ Completed processing!"
        lines = [
            f"✅ Live: {len(results.get('Live', []))}",
            f"🧊 Frozen: {len(results.get('Frozen', []))}",
            f"❌ Die: {len(results.get('Die', []))}",
        ]

    results_text = (
        f"<b>{title}</b>\n\n"
        f"📊 <b>Results:</b>\n" +
        "\n".join(lines) +
        f"\n\n📋 <b>Total: {total}</b>"
    )

    status_msg = await smart_edit(status_msg, results_text, reply_markup=back_to_check_kb(), parse_mode="HTML")

    # Send ZIP files per status (only for statuses with sessions)
    for status_name, phone_list in results.items():
        if not phone_list:
            continue

        tmp_zip = os.path.join(tempfile.gettempdir(), f"check_{status_name}.zip")
        try:
            session_count = 0
            with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as zf:
                for phone in phone_list:
                    session_file = os.path.join(sessions_dir, f"{phone}.session")
                    if os.path.exists(session_file):
                        zf.write(session_file, f"{phone}.session")
                        session_count += 1

            if session_count > 0:
                doc = FSInputFile(tmp_zip, filename=f"{status_name}.zip")
                caption = f"📦 {status_name}: {session_count} session"
                await context_msg.answer_document(doc, caption=caption)
                await asyncio.sleep(0.3)

        except Exception as e:
            logger.error(f"Failed to send {status_name} ZIP: {e}")
        finally:
            if os.path.exists(tmp_zip):
                os.remove(tmp_zip)
