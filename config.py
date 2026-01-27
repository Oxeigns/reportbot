import os

BOT_TOKEN = os.environ.get("BOT_TOKEN")
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH")
OWNER_ID = int(os.environ.get("OWNER_ID", 0))
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = "startlove"

SUDO_USERS = []
if sudo_str := os.environ.get("SUDO_USERS"):
    SUDO_USERS = [int(x.strip()) for x in sudo_str.split(",") if x.strip().isdigit()]
