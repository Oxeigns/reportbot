import asyncio
from pyrogram import Client
from pyrogram.errors import FloodWait, PeerFlood, ChatAdminRequired
from config import API_ID, API_HASH
from database import db
import logging

logging.basicConfig(level=logging.INFO)

class MassReporter:
    def __init__(self):
        self.clients = []
        self.active_clients = []
        
    async def load_sessions(self):
        sessions = await db.get_all_sessions()
        self.clients = []
        self.active_clients = []
        for session in sessions:
            session_id = session.get("_id")
            session_name = session.get("session_name") or session.get("name")
            session_string = (
                session.get("session_string")
                or session.get("session")
                or session.get("string")
                or session.get("session_str")
            )
            if not session_name and session_string and session_id:
                session_name = f"session_{session_id}"
                await db.normalize_session(session_id, session_name=session_name)
            if session_id and session_string and session.get("session_string") != session_string:
                await db.normalize_session(session_id, session_string=session_string)
            if not session_name or not session_string:
                logging.warning(
                    "Skipping session without required fields: %s",
                    session.get("_id", "unknown"),
                )
                continue
            try:
                client = Client(
                    session_name,
                    api_id=API_ID,
                    api_hash=API_HASH,
                    in_memory=True,
                    no_updates=True,
                    session_string=session_string,
                )
                await client.connect()
                try:
                    me = await client.get_me()
                except Exception:
                    await client.disconnect()
                    raise
                self.active_clients.append({
                    "client": client,
                    "session_name": session_name,
                    "user_id": me.id
                })
                await db.validate_session(session_name, "active")
            except Exception as e:
                if session_name:
                    await db.validate_session(session_name, "failed")
                logging.error(
                    "Session %s failed: %s",
                    session_name or "unknown",
                    e,
                )
        return len(self.active_clients)
    
    async def join_chat(self, chat_link):
        joined = 0
        for client_data in self.active_clients:
            try:
                client = client_data["client"]
                await client.join_chat(chat_link)
                joined += 1
                await asyncio.sleep(1)
            except Exception as e:
                logging.error(f"Failed to join {chat_link} with {client_data['session_name']}: {e}")
        return joined
    
    async def mass_report(self, target_chat, reason, description, report_count):
        success = 0
        failed = 0
        
        semaphore = asyncio.Semaphore(5)  # Limit concurrent reports
        
        async def report_with_client(client_data):
            async with semaphore:
                client = client_data["client"]
                try:
                    for i in range(report_count):
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
                except (PeerFlood, ChatAdminRequired):
                    return False
                except Exception:
                    return False
        
        tasks = []
        for client_data in self.active_clients:
            task = asyncio.create_task(report_with_client(client_data))
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, bool) and result:
                success += 1
            else:
                failed += 1
        
        return success, failed
