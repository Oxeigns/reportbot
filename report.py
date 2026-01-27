import asyncio
import logging
from pyrogram import Client
from pyrogram.errors import FloodWait, PeerFlood, UserAlreadyParticipant
from pyrogram.storage import StringSession
from config import API_ID, API_HASH
from database import db

logger = logging.getLogger(__name__)

class MassReporter:
    def __init__(self):
        self.active_clients = []

    async def load_sessions(self) -> int:
        """Load and validate all sessions from DB"""
        sessions = await db.get_all_sessions()
        self.active_clients.clear()
        
        for session in sessions:
            try:
                session_name = session.get("session_name")
                session_string = session.get("session_string")
                
                if not all([session_name, session_string]):
                    continue

                # ✅ FIXED: Pyrogram v2 session_string parameter
                client = Client(
                    session_name,
                    api_id=API_ID,
                    api_hash=API_HASH,
                    session_string=session_string,
                    in_memory=True
                )
                await client.start()
                
                # Test connection
                await client.get_me()
                
                self.active_clients.append({
                    "client": client,
                    "session_name": session_name
                })
                await db.validate_session(session_name, "active")
                
            except Exception as e:
                session_name = session.get("session_name", "unknown")
                await db.validate_session(session_name, "failed")
                logger.error(f"Session {session_name} failed: {e}")
        
        return len(self.active_clients)

    async def load_validated_sessions(self) -> int:
        """Load only active/validated sessions"""
        sessions = await db.get_active_sessions()
        self.active_clients.clear()
        
        for session in sessions:
            try:
                client = Client(
                    session["session_name"],
                    api_id=API_ID,
                    api_hash=API_HASH,
                    session_string=session["session_string"],
                    in_memory=True
                )
                await client.start()
                self.active_clients.append({
                    "client": client,
                    "session_name": session["session_name"]
                })
            except Exception as e:
                logger.error(f"Validated session failed: {e}")
        
        return len(self.active_clients)

    async def join_chat(self, chat_link: str) -> int:
        """Join target chat with all clients"""
        joined_count = 0
        for client_data in self.active_clients:
            try:
                client = client_data["client"]
                await client.join_chat(chat_link)
                joined_count += 1
                await asyncio.sleep(1)
            except (UserAlreadyParticipant, FloodWait) as e:
                if isinstance(e, FloodWait):
                    await asyncio.sleep(e.value)
                joined_count += 1
            except Exception:
                pass
        return joined_count

    async def mass_report(self, target_chat: str, reason: int, description: str, 
                         reports_per_session: int) -> tuple[int, int]:
        """Execute mass report"""
        success = 0
        failed = 0
        
        semaphore = asyncio.Semaphore(3)  # Limit concurrency
        
        async def report_client(client_data):
            async with semaphore:
                client = client_data["client"]
                try:
                    for _ in range(reports_per_session):
                        await client.report_chat(
                            chat_id=target_chat,
                            reason=reason,
                            message_ids=[],
                            description=description
                        )
                        await asyncio.sleep(2)
                    return True
                except FloodWait as e:
                    await asyncio.sleep(e.value)
                    return True
                except (PeerFlood, Exception):
                    return False
        
        # Run all reports concurrently
        tasks = [report_client(c) for c in self.active_clients]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, bool) and result:
                success += 1
            else:
                failed += 1
        
        return success, failed
