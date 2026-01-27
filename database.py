from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URL, DB_NAME

class Database:
    def __init__(self):
        self.client = AsyncIOMotorClient(MONGO_URL)
        self.db = self.client[DB_NAME]
        self.sessions = self.db.sessions
        self.sudos = self.db.sudos

    async def add_session(self, session_string: str, session_name: str):
        await self.sessions.update_one(
            {"session_name": session_name},
            {"$set": {"session_string": session_string, "status": "pending"}},
            upsert=True
        )

    async def get_all_sessions(self):
        return await self.sessions.find({}).to_list(None)

    async def get_active_sessions(self):
        return await self.sessions.find({"status": "active"}).to_list(None)

    async def get_total_session_count(self) -> int:
        return await self.sessions.count_documents({})

    async def get_active_session_count(self) -> int:
        return await self.sessions.count_documents({"status": "active"})

    async def validate_session(self, session_name: str, status: str):
        await self.sessions.update_one(
            {"session_name": session_name},
            {"$set": {"status": status}},
            upsert=True
        )

    async def add_sudo(self, user_id: int):
        await self.sudos.update_one(
            {"user_id": user_id},
            {"$set": {"user_id": user_id, "status": "active"}},
            upsert=True
        )

    async def remove_sudo(self, user_id: int):
        await self.sudos.delete_one({"user_id": user_id})

    async def is_sudo(self, user_id: int) -> bool:
        count = await self.sudos.count_documents({"user_id": user_id})
        return count > 0

    async def get_sudos(self):
        return await self.sudos.find({}).to_list(None)

db = Database()
