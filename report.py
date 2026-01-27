import asyncio
from pyrogram import Client
from pyrogram.errors import FloodWait, PeerFlood, ChatAdminRequired, UserAlreadyParticipant
from config import API_ID, API_HASH
from database import db
import logging

class MassReporter:
    def __init__(self):
        self.active_clients = []
        
    async def load_sessions(self):
        """Load and validate all sessions"""
        sessions = await db.get_all_sessions()
        self.active_clients = []
        
        for session in sessions:
            try:
                session_name = session.get("session_name")
                session_string = session.get("session_string")
                
                if not session_name or not session_string:
                    continue
                    
                client = Client(
                    session_name,
                    api_id=API_ID,
                    api_hash=API_HASH,
                    in_memory=True
                )
                await client.start(session_string=session_string)
                
                await client.get_me()  # Test connection
                self.active_clients.append({
                    "client": client,
                    "session_name": session_name
                })
                await db.validate_session(session_name, "active")
                
            except Exception as e:
                session_name = session.get("session_name")
                if session_name:
                    await db.validate_session(session_name, "failed")
                logging.error(f"Session failed: {e}")
        
        return len(self.active_clients)
    
    async def load_validated_sessions(self):
        """Load only active sessions"""
        sessions = await db.get_active_sessions()
        self.active_clients = []
        
        for session in sessions:
            try:
                client = Client(
                    session["session_name"],
                    api_id=API_ID,
                    api_hash=API_HASH,
                    in_memory=True
                )
                await client.start(session_string=session["session_string"])
                self.active_clients.append({
                    "client": client,
                    "session_name": session["session_name"]
                })
            except Exception:
                continue
        
        return len(self.active_clients)
    
    async def join_chat(self, chat_link: str) -> int:
        """Join chat with all active clients"""
        joined = 0
        for client_data in self.active_clients:
            try:
                client = client_data["client"]
                await client.join_chat(chat_link)
                joined += 1
                await asyncio.sleep(1)
            except (UserAlreadyParticipant, FloodWait) as e:
                if isinstance(e, FloodWait):
                    await asyncio.sleep(e.value)
                joined += 1
            except Exception:
                pass
        return joined
    
    async def mass_report(self, target_chat: str, reason: int, description: str, 
                         report_count: int) -> tuple[int, int]:
        """Mass report target"""
        success = 0
        failed = 0
        
        semaphore = asyncio.Semaphore(3)
        
        async def report_single_client(client_data):
            async with semaphore:
                client = client_data["client"]
                try:
                    for _ in range(report_count):
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
                except Exception:
                    return False
        
        tasks = [report_single_client(client_data) for client_data in self.active_clients]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, bool) and result:
                success += 1
            else:
                failed += 1
        
        return success, failed
