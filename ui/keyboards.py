"""
Inline Keyboards — All bot keyboards defined here.
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


# ─── Main Menu ───────────────────────────────────────────────────────────────

def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Register Number", callback_data="reg")],
        [
            InlineKeyboardButton(text="📂 Sessions", callback_data="ses"),
            InlineKeyboardButton(text="📥 Import", callback_data="imp_menu"),
        ],
        [
            InlineKeyboardButton(text="📊 Statistics", callback_data="ss"),
            InlineKeyboardButton(text="📦 Export All", callback_data="se"),
        ],
        [
            InlineKeyboardButton(text="🔍 Check", callback_data="chk"),
            InlineKeyboardButton(text="👤 Profile", callback_data="prf_apply"),
        ],
        [
            InlineKeyboardButton(text="⏰ Scheduler", callback_data="scheduler"),
            InlineKeyboardButton(text="👥 Admins", callback_data="adm_menu"),
        ],
        [InlineKeyboardButton(text="📈 Charts", callback_data="stats_chart")],
        [InlineKeyboardButton(text="🌐 Panel", callback_data="panel")],
        [InlineKeyboardButton(text="⚙️ Settings", callback_data="set")],
    ])


# ─── Sessions ────────────────────────────────────────────────────────────────

def sessions_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌍 View by Country", callback_data="sl:0")],
        [InlineKeyboardButton(text="🔍 Search", callback_data="search")],
        [InlineKeyboardButton(text="📊 Statistics", callback_data="ss")],
        [InlineKeyboardButton(text="📦 Export All (ZIP)", callback_data="se")],
        [InlineKeyboardButton(text="📦 Export by Status", callback_data="ses_exp_status")],
        [InlineKeyboardButton(text="🚪 Log Out All", callback_data="loa")],
        [InlineKeyboardButton(text="🧹 Delete All Dead", callback_data="del_dead")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="menu")],
    ])


def countries_list_kb(countries: dict[str, int], page: int = 0, per_page: int = 8) -> InlineKeyboardMarkup:
    """
    Build paginated country list.
    countries: {folder_name: (flag, display_name, count)}
    """
    items = list(countries.items())
    total_pages = max(1, (len(items) + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))

    start = page * per_page
    end = start + per_page
    page_items = items[start:end]

    rows = []
    for folder, (flag, name, count) in page_items:
        rows.append([InlineKeyboardButton(
            text=f"{flag} {name} ({count})",
            callback_data=f"sc:{folder[:50]}",
        )])

    # Pagination row
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Prev", callback_data=f"sl:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"sl:{page + 1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(text="🔙 Back", callback_data="ses")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def country_sessions_kb(folder: str, phones: list[str], page: int = 0, per_page: int = 5) -> InlineKeyboardMarkup:
    """Show phones for a country with delete/logout buttons (paginated)."""
    total_pages = max(1, (len(phones) + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))

    start = page * per_page
    end = start + per_page
    page_phones = phones[start:end]

    rows = []
    for phone in page_phones:
        rows.append([
            InlineKeyboardButton(text=f"📱 +{phone}", callback_data=f"sp:{phone}"),
        ])

    # Pagination row (3 buttons: Previous, Page Info, Next)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Previous", callback_data=f"scp:{folder[:40]}:{page - 1}"))
    else:
        nav.append(InlineKeyboardButton(text="⬅️ Previous", callback_data="noop"))
    nav.append(InlineKeyboardButton(text=f"📄 {page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"scp:{folder[:40]}:{page + 1}"))
    else:
        nav.append(InlineKeyboardButton(text="Next ➡️", callback_data="noop"))
    rows.append(nav)

    rows.append([
        InlineKeyboardButton(text="🚪 Log Out All", callback_data=f"loac:{folder[:40]}"),
        InlineKeyboardButton(text="🗑 Delete All", callback_data=f"dac:{folder[:40]}"),
    ])
    rows.append([
        InlineKeyboardButton(text="📦 Export Country", callback_data=f"sec:{folder[:50]}"),
        InlineKeyboardButton(text="✂️ Split", callback_data=f"spl:{folder[:45]}"),
    ])
    rows.append([
        InlineKeyboardButton(text="📦 Export by Status", callback_data=f"c_es:{folder[:40]}"),
    ])
    rows.append([InlineKeyboardButton(text="🔙 Back", callback_data="sl:0")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def phone_detail_kb(phone: str, folder: str) -> InlineKeyboardMarkup:
    """Show detail view for a single phone with log out, delete, get otp, and back."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📨 Get OTP", callback_data=f"otp:{phone}")],
        [InlineKeyboardButton(text="📋 Other Sessions", callback_data=f"other_sess:{phone}")],
        [InlineKeyboardButton(text="🚪 Log Out", callback_data=f"lo:{phone}")],
        [InlineKeyboardButton(text="🗑 Delete", callback_data=f"sd:{phone}")],
        [InlineKeyboardButton(text="🔙 Back", callback_data=f"sc:{folder[:50]}")],
    ])


def import_session_kb(phone: str) -> InlineKeyboardMarkup:
    """Keyboard for specifically imported floating sessions."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📨 Get Code", callback_data=f"imp_otp:{phone}")],
        [InlineKeyboardButton(text="🚪 Log Out", callback_data=f"imp_lo:{phone}")],
        [InlineKeyboardButton(text="🗑 Delete", callback_data=f"imp_del:{phone}")],
    ])


def country_export_status_kb(folder: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🟢 Export FREE", callback_data=f"ce:FREE:{folder[:40]}"),
            InlineKeyboardButton(text="✂️ Split", callback_data=f"spls:FREE:{folder[:30]}"),
        ],
        [
            InlineKeyboardButton(text="🟡 Export SPAM", callback_data=f"ce:SPAM:{folder[:40]}"),
            InlineKeyboardButton(text="✂️ Split", callback_data=f"spls:SPAM:{folder[:30]}"),
        ],
        [
            InlineKeyboardButton(text="🔴 Export BANNED", callback_data=f"ce:BANNED:{folder[:40]}"),
            InlineKeyboardButton(text="✂️ Split", callback_data=f"spls:BANNED:{folder[:30]}"),
        ],
        [
            InlineKeyboardButton(text="🔵 Export NEW_REGISTERED", callback_data=f"ce:NEW_REGISTERED:{folder[:40]}"),
            InlineKeyboardButton(text="✂️ Split", callback_data=f"spls:NEW_REGISTERED:{folder[:20]}"),
        ],
        [
            InlineKeyboardButton(text="✅ Contact NoLimit", callback_data=f"ce_c:NoLimit:{folder[:35]}"),
            InlineKeyboardButton(text="⚠️ Contact Limited", callback_data=f"ce_c:Limited:{folder[:35]}"),
        ],
        [InlineKeyboardButton(text="🔙 Back", callback_data=f"sc:{folder[:40]}")],
    ])


# ─── Search ──────────────────────────────────────────────────────────────────

def search_result_kb(phone: str, folder: str) -> InlineKeyboardMarkup:
    """Post-search: actions for a found phone."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚪 Log Out", callback_data=f"lo:{phone}")],
        [InlineKeyboardButton(text="🗑 Delete", callback_data=f"sd:{phone}")],
        [InlineKeyboardButton(text="📨 Get OTP", callback_data=f"otp:{phone}")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="ses")],
    ])


def otp_result_kb(phone: str, found: bool) -> InlineKeyboardMarkup:
    """OTP result: retry, back, and optionally keep/logout."""
    rows = []
    if found:
        rows.append([InlineKeyboardButton(text="🔄 Fetch Again", callback_data=f"otp:{phone}")])
        rows.append([InlineKeyboardButton(text="📋 Other Sessions", callback_data=f"other_sess:{phone}")])
        rows.append([
            InlineKeyboardButton(text="✅ Keep Session", callback_data=f"otp_keep:{phone}"),
            InlineKeyboardButton(text="🚪 Log Out Session", callback_data=f"otp_lo:{phone}"),
        ])
    else:
        rows.append([InlineKeyboardButton(text="🔄 Fetch Again", callback_data=f"otp:{phone}")])
    rows.append([InlineKeyboardButton(text="🔙 Back", callback_data="ses")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─── Bulk Action Choice ─────────────────────────────────────────────────────

def bulk_action_choice_kb(action: str, folder: str) -> InlineKeyboardMarkup:
    """Choose between all numbers or specific numbers for log out / delete."""
    # action: "lo" (log out) or "da" (delete)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 All Numbers", callback_data=f"bulk_all_{action}:{folder[:35]}")],
        [InlineKeyboardButton(text="📝 Specific Numbers", callback_data=f"bulk_sp_{action}:{folder[:35]}")],
        [InlineKeyboardButton(text="🔙 Cancel", callback_data=f"sc:{folder[:50]}")],
    ])


# ─── Confirm / Delete ────────────────────────────────────────────────────────

def confirm_delete_kb(phone: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Yes, Delete", callback_data=f"sdc:{phone}"),
            InlineKeyboardButton(text="❌ Cancel", callback_data="ses"),
        ],
    ])


def confirm_logout_kb(phone: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Yes, Log Out", callback_data=f"loc:{phone}"),
            InlineKeyboardButton(text="❌ Cancel", callback_data="ses"),
        ],
    ])


def confirm_logout_all_kb(step: int = 1) -> InlineKeyboardMarkup:
    """3-step confirmation for global log out all."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"✅ Yes, Confirm ({step}/3)", callback_data=f"loag:{step}"),
            InlineKeyboardButton(text="❌ Cancel", callback_data="ses"),
        ],
    ])


def confirm_logout_all_country_kb(folder: str, step: int = 1) -> InlineKeyboardMarkup:
    """3-step confirmation for per-country log out all."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"✅ Yes, Confirm ({step}/3)", callback_data=f"loacc:{folder[:35]}:{step}"),
            InlineKeyboardButton(text="❌ Cancel", callback_data=f"sc:{folder[:50]}"),
        ],
    ])


def confirm_delete_all_country_kb(folder: str, step: int = 1) -> InlineKeyboardMarkup:
    """3-step confirmation for per-country delete all."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"✅ Yes, Confirm ({step}/3)", callback_data=f"dacc:{folder[:35]}:{step}"),
            InlineKeyboardButton(text="❌ Cancel", callback_data=f"sc:{folder[:50]}"),
        ],
    ])


def export_status_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 Export FREE", callback_data="exp_status:FREE")],
        [InlineKeyboardButton(text="🟡 Export SPAM", callback_data="exp_status:SPAM")],
        [InlineKeyboardButton(text="🔴 Export BANNED", callback_data="exp_status:BANNED")],
        [InlineKeyboardButton(text="🔵 Export NEW_REGISTERED", callback_data="exp_status:NEW_REGISTERED")],
        [
            InlineKeyboardButton(text="✅ Contact NoLimit", callback_data="exp_cstatus:NoLimit"),
            InlineKeyboardButton(text="⚠️ Contact Limited", callback_data="exp_cstatus:Limited"),
        ],
        [InlineKeyboardButton(text="🔙 Back", callback_data="ses")],
    ])


# ─── Settings ────────────────────────────────────────────────────────────────

def settings_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Proxy Settings", callback_data="prx")],
        [InlineKeyboardButton(text="🔑 API Settings", callback_data="api")],
        [InlineKeyboardButton(text="👤 Profile", callback_data="profile")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="menu")],
    ])


def proxy_kb(is_enabled: bool = True) -> InlineKeyboardMarkup:
    toggle_text = "🔴 Disable Proxy" if is_enabled else "🟢 Enable Proxy"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle_text, callback_data="ptgl")],
        [InlineKeyboardButton(text="✏️ Change Proxy", callback_data="pe")],
        [InlineKeyboardButton(text="🧪 Test Connection", callback_data="pt")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="set")],
    ])


def api_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Change API ID", callback_data="ai")],
        [InlineKeyboardButton(text="✏️ Change API Hash", callback_data="ah")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="set")],
    ])


def profile_kb(p: dict) -> InlineKeyboardMarkup:
    """Profile auto-fill settings keyboard showing current status for each option."""
    u_icon = "✅" if p.get("auto_username") else "❌"
    n_icon = "✅" if p.get("auto_name") else "❌"
    ph_icon = "✅" if p.get("auto_photo") else "❌"
    b_icon = "✅" if p.get("auto_bio") else "❌"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{u_icon} Username", callback_data="prf_username")],
        [InlineKeyboardButton(text=f"{n_icon} Name", callback_data="prf_name")],
        [InlineKeyboardButton(text=f"{ph_icon} Profile Photo", callback_data="prf_photo")],
        [InlineKeyboardButton(text=f"{b_icon} Bio", callback_data="prf_bio")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="set")],
    ])


# ─── Common ──────────────────────────────────────────────────────────────────

def back_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu")],
    ])


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel")],
    ])


# ─── Check ───────────────────────────────────────────────────────────────────

def check_menu_kb() -> InlineKeyboardMarkup:
    """Menu with 3 check types."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Spam Check", callback_data="chk_type:spam")],
        [InlineKeyboardButton(text="📇 Contact Limit Check", callback_data="chk_type:contact")],
        [InlineKeyboardButton(text="✅ Session Validity Check", callback_data="chk_type:alive")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="menu")],
    ])


def check_countries_list_kb(countries: dict[str, int], check_type: str, page: int = 0, per_page: int = 8) -> InlineKeyboardMarkup:
    """
    Build paginated country list for check feature.
    countries: {folder_name: (flag, display_name, count)}
    check_type: 'spam', 'contact', or 'alive'
    """
    items = list(countries.items())
    total_pages = max(1, (len(items) + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))

    start = page * per_page
    end = start + per_page
    page_items = items[start:end]

    rows = []
    for folder, (flag, name, count) in page_items:
        rows.append([InlineKeyboardButton(
            text=f"{flag} {name} ({count})",
            callback_data=f"chkc:{check_type}:{folder[:40]}",
        )])

    # Pagination row
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Prev", callback_data=f"chkl:{check_type}:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"chkl:{check_type}:{page + 1}"))
    if nav:
        rows.append(nav)

    # Upload ZIP button
    rows.append([InlineKeyboardButton(text="📤 Upload ZIP to Check", callback_data=f"chk_zip:{check_type}")])
    rows.append([InlineKeyboardButton(text="🔙 Back", callback_data="chk")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_to_check_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back to Check Menu", callback_data="chk")],
    ])


# ─── Profile Apply ────────────────────────────────────────────────────────────

def profile_apply_menu_kb() -> InlineKeyboardMarkup:
    """Menu to choose apply profile target: ZIP file or a country."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Upload ZIP", callback_data="prf_zip")],
        [InlineKeyboardButton(text="🌍 Apply to Country", callback_data="prf_country:0")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="menu")],
    ])


def profile_apply_countries_kb(countries: dict, page: int = 0, per_page: int = 8) -> InlineKeyboardMarkup:
    """Paginated country list for profile apply."""
    items = list(countries.items())
    total_pages = max(1, (len(items) + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))

    start = page * per_page
    end = start + per_page
    page_items = items[start:end]

    rows = []
    for folder, (flag, name, count) in page_items:
        rows.append([InlineKeyboardButton(
            text=f"{flag} {name} ({count})",
            callback_data=f"prf_c:{folder[:50]}",
        )])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Prev", callback_data=f"prf_country:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"prf_country:{page + 1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(text="🔙 Back", callback_data="prf_apply")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_to_profile_apply_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back to Profile Apply", callback_data="prf_apply")],
    ])


# ─── Delete Dead Confirm ──────────────────────────────────────────────────────

def confirm_delete_dead_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Yes, Delete All Dead", callback_data="del_dead_confirm"),
            InlineKeyboardButton(text="❌ Cancel", callback_data="ses"),
        ],
    ])
