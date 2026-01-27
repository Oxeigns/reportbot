import re
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URL, DB_NAME
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.client = AsyncIOMotorClient(MONGO_URL)
        self.db = self.client[DB_NAME]
        self.sessions = self.db.sessions
        self.sudos = self.db.sudos
        self.reports = self.db.reports  # New reports collection

    def is_valid_session_string(self, session_string: str) -> bool:
        """🔥 Check if session string is valid format"""
        # Pyrogram v2 session string pattern
        if not session_string or len(session_string) < 100:
            return False
        if session_string.startswith("1"):
            return True
        return "BV" in session_string and len(session_string) > 200

    async def add_session(self, session_string: str, session_name: str = None):
        """Add session with validation"""
        if not self.is_valid_session_string(session_string):
            return False, "❌ Invalid session format!"
        
        if not session_name:
            session_name = f"session_{await self.get_total_session_count() + 1}"
        
        await self.sessions.update_one(
            {"session_name": session_name},
            {
                "$set": {
                    "session_string": session_string,
                    "status": "pending",
                    "last_error": None
                },
                "$currentDate": {"added_at": True}
            },
            upsert=True
        )
        return True, f"✅ Added: {session_name}"

    async def get_all_sessions(self):
        return await self.sessions.find({}).sort("added_at", -1).to_list(None)

    async def get_active_sessions(self):
        return await self.sessions.find({"status": "active"}).to_list(None)

    async def get_pending_sessions(self):
        return await self.sessions.find({
            "$or": [
                {"status": "pending"},
                {"status": {"$exists": False}},
                {"status": None},
                {"status": ""}
            ]
        }).to_list(None)

    async def get_failed_sessions(self):
        return await self.sessions.find({"status": "failed"}).to_list(None)

    async def get_total_session_count(self) -> int:
        return await self.sessions.count_documents({})

    async def get_active_session_count(self) -> int:
        return await self.sessions.count_documents({"status": "active"})

    async def ensure_session_name(self, session: dict) -> Optional[str]:
        """Ensure a session has a name and persist it."""
        session_name = session.get("session_name")
        if session_name:
            return session_name
        session_id = session.get("_id")
        if not session_id:
            return None
        session_name = f"session_{session_id}"
        await self.sessions.update_one(
            {"_id": session_id},
            {"$set": {"session_name": session_name}}
        )
        return session_name

    async def update_session_status(self, session_name: str, status: str, error: str = None):
        """🔥 Update with error info"""
        update_data = {"status": status}
        if error:
            update_data["last_error"] = error
        await self.sessions.update_one(
            {"session_name": session_name},
            {"$set": update_data, "$currentDate": {"validated_at": True}}
        )

    async def get_stats(self):
        total = await self.get_total_session_count()
        active = await self.get_active_session_count()
        pending = await self.sessions.count_documents({
            "$or": [
                {"status": "pending"},
                {"status": {"$exists": False}},
                {"status": None},
                {"status": ""}
            ]
        })
        failed = await self.sessions.count_documents({"status": "failed"})
        sudo_count = await self.sudos.count_documents({})
        
        return {
            "total": total, "active": active, "pending": pending, 
            "failed": failed, "sudo": sudo_count
        }

    # SUDO Functions
    async def add_sudo(self, user_id: int):
        await self.sudos.update_one({"user_id": user_id}, {"$set": {"status": "active"}}, upsert=True)

    async def remove_sudo(self, user_id: int):
        await self.sudos.delete_one({"user_id": user_id})

    async def is_sudo(self, user_id: int) -> bool:
        return await self.sudos.count_documents({"user_id": user_id}) > 0

    async def get_sudo_ids(self) -> list[int]:
        records = await self.sudos.find({}, {"_id": 0, "user_id": 1}).sort("user_id", 1).to_list(None)
        return [record["user_id"] for record in records if "user_id" in record]

db = Database()
