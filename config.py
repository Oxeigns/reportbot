import os

# Bot Configuration
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
OWNER_ID = int(os.environ.get("OWNER_ID", 0))
MONGO_URL = os.environ.get("MONGO_URL", "")
DB_NAME = os.environ.get("DB_NAME", "startlove")

# Sudo Users (comma separated)
SUDO_USERS = [int(x) for x in os.environ.get("SUDO_USERS", "").split(",") if x.strip().isdigit()]

# Buttons
REPORT_BUTTON = "🚨 Send Report"
ADD_SUDO_BUTTON = "➕ Add Sudo"
REMOVE_SUDO_BUTTON = "➖ Remove Sudo"
STATS_BUTTON = "📊 Stats"
BACK_BUTTON = "🔙 Back"
