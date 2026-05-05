"""
FSM States for the bot conversations.
"""
from aiogram.fsm.state import State, StatesGroup


class RegState(StatesGroup):
    """Registration flow states."""
    phone = State()       # Waiting for phone number
    code = State()        # Waiting for verification code
    password = State()    # Waiting for 2FA password


class ProxyState(StatesGroup):
    """Proxy editing states."""
    waiting = State()     # Waiting for new proxy string


class ApiState(StatesGroup):
    """API settings editing states."""
    api_id = State()      # Waiting for new API ID
    api_hash = State()    # Waiting for new API Hash


class SplitState(StatesGroup):
    """Split export states."""
    count = State()       # Waiting for number of sessions to extract


class SearchState(StatesGroup):
    """Search phone states."""
    phone = State()       # Waiting for phone number to search


class BulkActionState(StatesGroup):
    """Bulk action (specific phones) states."""
    phones = State()      # Waiting for phone list (message or .txt file)


class ImportState(StatesGroup):
    """Import sessions state."""
    waiting_for_file = State()
    action_choice = State()  # Choose between save only or fetch OTPs


class CheckState(StatesGroup):
    """Check sessions state."""
    waiting_for_zip = State()  # Waiting for ZIP file to check


class ProfileApplyState(StatesGroup):
    """Apply profile to sessions state."""
    waiting_for_zip = State()  # Waiting for ZIP file to apply profile on


# ProfileState removed — profile options are now pure toggles (no user input needed)
