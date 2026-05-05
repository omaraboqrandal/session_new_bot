"""
Start & Main Menu handler.
"""

from aiogram import Router, F
from utils.utils import smart_edit
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

from ui.keyboards import main_menu_kb
from utils.country_utils import get_total_stats
from handlers.common import is_admin_async, is_write_admin_async
from handlers.register import cleanup_registration

router = Router()


# ─── /start ──────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    if not await is_admin_async(message.from_user.id):
        await message.answer("🚫 You are not authorized to use this bot.")
        return

    await state.clear()
    total, countries = get_total_stats()

    text = (
        "🏠 <b>Session Manager</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 Sessions: <b>{total}</b>  •  🌍 Countries: <b>{countries}</b>\n\n"
        "Choose an option below:"
    )
    await message.answer(text, reply_markup=main_menu_kb(), parse_mode="HTML")


# ─── Main Menu callback ─────────────────────────────────────────────────────

@router.callback_query(F.data == "menu")
async def cb_menu(callback: CallbackQuery, state: FSMContext):
    if not await is_admin_async(callback.from_user.id):
        await callback.answer("🚫 Not authorized", show_alert=True)
        return

    await state.clear()
    total, countries = get_total_stats()

    text = (
        "🏠 <b>Session Manager</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 Sessions: <b>{total}</b>  •  🌍 Countries: <b>{countries}</b>\n\n"
        "Choose an option below:"
    )
    await smart_edit(callback.message, text, reply_markup=main_menu_kb(), parse_mode="HTML")
    await callback.answer()


# ─── Cancel ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    if not await is_admin_async(callback.from_user.id):
        await callback.answer("🚫 Not authorized", show_alert=True)
        return

    await cleanup_registration(callback.from_user.id)
    await state.clear()
    total, countries = get_total_stats()

    text = (
        "🏠 <b>Session Manager</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 Sessions: <b>{total}</b>  •  🌍 Countries: <b>{countries}</b>\n\n"
        "Choose an option below:"
    )
    await smart_edit(callback.message, text, reply_markup=main_menu_kb(), parse_mode="HTML")
    await callback.answer("❌ Cancelled")


# ─── Noop ────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery):
    await callback.answer()
