from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URL, DB_NAME
import asyncio

class Database:
    def __init__(self):
        self.client = AsyncIOMotorClient(MONGO_URL)
        self.db = self.client[DB_NAME]
        self.sessions = self.db.sessions
        self.sudos = self.db.sudos
        
    async def add_session(self, session_string, session_name):
        await self.sessions.update_one(
            {"session_name": session_name},
            {"$set": {"session_string": session_string, "status": "pending"}},
            upsert=True
        )
        
    async def get_all_sessions(self):
        return await self.sessions.find({}).to_list(length=None)
    
    async def validate_session(self, session_name, status):
        await self.sessions.update_one(
            {"session_name": session_name},
            {"$set": {"status": status}}
        )

    async def normalize_session(self, session_id, session_name=None, session_string=None):
        if not session_id:
            return
        updates = {}
        if session_name:
            updates["session_name"] = session_name
        if session_string:
            updates["session_string"] = session_string
        if updates:
            await self.sessions.update_one(
                {"_id": session_id},
                {"$set": updates},
            )
    
    async def get_active_session_count(self):
        return await self.sessions.count_documents({"status": "active"})

    async def get_total_session_count(self):
        return await self.sessions.count_documents({})
    
    async def add_sudo(self, user_id):
        await self.sudos.update_one(
            {"user_id": user_id},
            {"$set": {"user_id": user_id, "status": "active"}},
            upsert=True
        )
    
    async def remove_sudo(self, user_id):
        await self.sudos.delete_one({"user_id": user_id})
    
    async def is_sudo(self, user_id):
        count = await self.sudos.count_documents({"user_id": user_id})
        return count > 0
    
    async def get_sudos(self):
        return await self.sudos.find({}).to_list(length=None)

db = Database()
