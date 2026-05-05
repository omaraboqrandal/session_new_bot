"""
Session Worker — Telethon client handling for registration and proxy testing.
"""

import socks
import asyncio
import re
import logging
from telethon import TelegramClient,events
from telethon.errors import (
    PhoneNumberInvalidError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    SessionPasswordNeededError,
    FloodWaitError,
    PhoneNumberBannedError,
)
import random



system_version = "Windows 10"
app_version = "6.7.8 x64"
lang_code = "en"

# Re-export errors for handlers
__all__ = [
    "get_proxy_tuple",
    "create_client",
    "test_proxy_connection",
    "check_spam",
    "check_contact_limit",
    "check_session_alive",
    "PhoneNumberInvalidError",
    "PhoneCodeInvalidError",
    "PhoneCodeExpiredError",
    "SessionPasswordNeededError",
    "FloodWaitError",
    "PhoneNumberBannedError",
]


def get_proxy_tuple(proxy_config: dict) -> tuple | None:
    """Convert proxy dict to Telethon proxy tuple."""
    if not proxy_config.get("enabled", True):
        return None

    type_map = {
        "socks5": socks.SOCKS5,
        "socks4": socks.SOCKS4,
        "http": socks.HTTP,
    }
    return (
        type_map.get(proxy_config.get("type", "socks5"), socks.SOCKS5),
        proxy_config["host"],
        int(proxy_config["port"]),
        proxy_config.get("rdns", True),
        proxy_config.get("username", ""),
        proxy_config.get("password", ""),
    )



def create_client(session_path: str, api_id: int, api_hash: str, proxy_config: dict) -> TelegramClient:
    """Create a TelegramClient with the given proxy."""
    proxy_tuple = get_proxy_tuple(proxy_config)
    return TelegramClient(
        session_path,
        api_id, api_hash,
        proxy=proxy_tuple,
        device_model="MS-" + ''.join(random.choices("1234567890", k=6)),
        system_version=system_version,
        app_version=app_version, 
        lang_code=lang_code
    )


async def test_proxy_connection(api_id: int, api_hash: str, proxy_config: dict) -> tuple[bool, str]:
    """
    Test proxy connection by connecting to Telegram.
    Returns (success, message).
    """
    import tempfile
    import os

    tmp_session = os.path.join(tempfile.gettempdir(), "_proxy_test_session")
    client = create_client(tmp_session, api_id, api_hash, proxy_config)

    try:
        await client.connect()
        await client.disconnect()

        # Cleanup test session
        for ext in ["", ".session", ".session-journal"]:
            path = tmp_session + ext
            if os.path.exists(path):
                os.remove(path)

        return True, "✅ Proxy connection successful!"
    except Exception as e:
        # Cleanup
        try:
            await client.disconnect()
        except Exception:
            pass
        for ext in ["", ".session", ".session-journal"]:
            path = tmp_session + ext
            if os.path.exists(path):
                os.remove(path)

        return False, f"❌ Connection failed: {type(e).__name__}: {e}"




async def check_spam(client: TelegramClient) -> str:
    """
    يرسل /start لـ @SpamBot ويقوم بمعالجة الرد فور وصوله.
    """
    spam_bot = "@SpamBot"
    result = "UNKNOWN"
    
    # تعريف الأنماط
    spam_patterns = [
    r"\bsorry\b", r"\bhet spijt me\b", r"\bes tut mir wirklich leid\b",
    r"\bsaya meminta maaf\b", r"\bsono davvero dispiaciuto\b",
    r"بسيار متأسفم", r"\bsinto muito\b", r"очень жаль",
    r"siento mucho", r"juda afsusdaman", r"نعتذر بشدة",
    
    # الإضافات الجديدة (العربية، الإنجليزية، والفارسية)
    r"للأسف وجد بعض مستخدمي تيليجرام رسائلك مزعجة",
    r"I’m afraid some Telegram users found your messages annoying",
    r"به اطلاعتان می‌رسانیم برخی از کاربران تلگرام پیام‌های شما را آزاردهنده دانسته"
]

    ok_patterns = [
        r"رائع", r"goed nieuws", r"good news", r"gute nachrichten",
        r"kabar baik", r"buone notizie", r"berita baik", r"مژده",
        r"boas notícias", r"ваш аккаунт свободен", r"buenas noticias", r"sizga xushxabar"
    ]
    banned_patterns = [
        r"\byour account was blocked\b", r"\baccount was banned\b",
        r"\byou are banned\b", r"\bpermanently blocked\b"
    ]
    warning_texts = [
        "unfortunately, some phone numbers may trigger a harsh response",
        "للأسف، قد تسبب بعض أرقام الهواتف", "helaas reageert ons anti-spamsysteem harder",
        "leider können einige Telefonnummern", "sayang sekali, beberapa nomor ponsel",
        "sfortunatamente, alcuni numeri di telefono", "malangnya, setengah nombor fon",
        "بسيار متأسفم كه گاهى بعضى از شمارههاى تلفن", "infelizmente, algunos números de telefone",
        "к сожалению, иногда наша антиспам-система", "lamentablemente, algunos números de teléfono",
        "afsuski, ayrim telefon raqamlari"
    ]

    # حدث لانتظار الرد
    event_received = asyncio.Event()

    @client.on(events.NewMessage(from_users=spam_bot))
    async def handler(event):
        nonlocal result
        text = event.raw_text.lower()
        
        if any(re.search(p, text) for p in spam_patterns):
            result = "SPAM"
        elif any(w.lower() in text for w in warning_texts):
            result = "NEW_REGISTERED"
        elif any(re.search(p, text) for p in ok_patterns):
            result = "FREE"
        elif any(re.search(p, text) for p in banned_patterns):
            result = "BANNED"
            await client.log_out()
        
        event_received.set()

    try:
        # إرسال الرسالة للبدء
        await client.send_message(spam_bot, "/start")
        
        # انتظار الرد لمدة أقصاها 10 ثوانٍ (timeout) لتجنب التعليق
        try:
            await asyncio.wait_for(event_received.wait(), timeout=10)
        except asyncio.TimeoutError:
            result = "UNKNOWN"

    except Exception:
        logging.exception("check_spam error")
    finally:
        # إزالة الـ handler فوراً
        client.remove_event_handler(handler)
        # حذف المحادثة بعد الانتهاء
        try:
            await client.delete_dialog(spam_bot)
        except:
            pass

    return result


async def check_contact_limit(client: TelegramClient) -> str:
    """
    Check if the account is limited from adding new contacts.
    Uses ImportContactsRequest with a test number.
    Returns: "NoLimit", "Limited", or "UNKNOWN".
    """
    try:
        from telethon.tl.functions.contacts import ImportContactsRequest, DeleteContactsRequest
        from telethon.tl.types import InputPhoneContact

        contact = InputPhoneContact(
            client_id=0,
            phone="+970568502325",
            first_name="TEST",
            last_name="Ali"
        )

        result = await client(ImportContactsRequest([contact]))

        if result.users:
            await client(DeleteContactsRequest(id=result.users))
            return "NoLimit"
        else:
            await client(DeleteContactsRequest(id=result.users))
            return "Limited"

    except Exception:
        logging.exception("check_contact_limit error")
        return "UNKNOWN"


async def check_session_alive(client: TelegramClient) -> str:
    """
    Check if a session is still authorized (alive).
    Returns: "Live" or "Die".
    """
    try:
        if await client.is_user_authorized():
            return "Live"
        else:
            return "Die"
    except Exception:
        logging.exception("check_session_alive error")
        return "Die"


async def get_last_otp(client: TelegramClient) -> tuple[bool, str]:
    """
    Fetch the last OTP/verification code from Telegram service messages.
    Looks in messages from user 777000 (Telegram) for codes.
    Returns (found: bool, code_or_message: str).
    """
    try:
        # Try getting messages from Telegram service (user ID 777000)
        codes_found = []
        try:
            async for msg in client.iter_messages(777000, limit=5):
                if msg.message:
                    # Look for numeric codes (4-8 digits)
                    import re
                    matches = re.findall(r'\b(\d{4,8})\b', msg.message)
                    if matches:
                        codes_found.append({
                            "code": matches[0],
                            "date": msg.date.strftime("%Y-%m-%d %H:%M:%S") if msg.date else "Unknown"
                        })
        except Exception:
            pass

        if codes_found:
            latest = codes_found[0]
            return True, (
                f"🔑 <b>Code:</b> <code>{latest['code']}</code>\n"
                f"📅 <b>Date:</b> {latest['date']}\n\n"
            )

        return False, "📭 No verification codes found."

    except Exception as e:
        logging.exception("get_last_otp error")
        return False, f"❌ Error: {type(e).__name__}: {e}"

