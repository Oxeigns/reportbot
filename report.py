import asyncio
import logging
from pyrogram import Client
from pyrogram.errors import FloodWait, SessionPasswordNeeded, PhoneCodeInvalid, IncorrectPaddingError
from config import API_ID, API_HASH
from database import db

logger = logging.getLogger(__name__)

class SessionValidator:
    @staticmethod
    async def test_session(session_string: str, session_name: str) -> tuple[bool, str]:
        """🔥 ROBUST session testing - handles all errors"""
        try:
            client = Client(
                session_name,
                api_id=API_ID,
                api_hash=API_HASH,
                session_string=session_string,
                in_memory=True,
                no_updates=True  # 🔥 Speed optimization
            )
            
            await client.start()
            me = await client.get_me()
            await client.stop()
            
            return True, f"✅ {me.first_name}"
            
        except IncorrectPaddingError:
            return False, "❌ Incorrect padding - REGENERATE session"
        except FloodWait as e:
            return False, f"⏳ FloodWait {e.value}s"
        except Exception as e:
            return False, f"❌ {str(e)[:50]}"

class MassReporter:
    def __init__(self):
        self.active_clients = []

    async def validate_all_sessions(self) -> dict:
        """🔥 VALIDATE ALL with detailed errors"""
        pending = await db.get_pending_sessions()
        failed = await db.get_failed_sessions()
        
        # Re-validate failed sessions first
        all_to_validate = failed + pending
        
        results = {"active": 0, "failed": 0, "total": len(all_to_validate)}
        
        for session in all_to_validate:
            session_name = session["session_name"]
            session_string = session["session_string"]
            
            success, message = await SessionValidator.test_session(session_string, session_name)
            status = "active" if success else "failed"
            
            await db.update_session_status(session_name, status, message if not success else None)
            
            if success:
                results["active"] += 1
            else:
                results["failed"] += 1
        
        return results

    async def load_active_clients(self) -> int:
        """Load only VALIDATED active sessions"""
        sessions = await db.get_active_sessions()
        self.active_clients.clear()
        
        for session in sessions:
            try:
                client = Client(
                    session["session_name"],
                    api_id=API_ID,
                    api_hash=API_HASH,
                    session_string=session["session_string"],
                    in_memory=True,
                    no_updates=True
                )
                await client.start()
                self.active_clients.append({
                    "client": client,
                    "name": session["session_name"]
                })
            except:
                continue
        
        return len(self.active_clients)

    async def join_target_chat(self, chat_link: str) -> int:
        """Join target chat"""
        joined = 0
        semaphore = asyncio.Semaphore(2)
        
        async def join_one(client_data):
            async with semaphore:
                try:
                    chat = await client_data["client"].join_chat(chat_link)
                    return True
                except:
                    return False
        
        tasks = [join_one(c) for c in self.active_clients]
        results = await asyncio.gather(*tasks)
        return sum(results)

    async def mass_report_chat(self, target_chat: str, reason: int = 1, description: str = "") -> dict:
        """Mass report with concurrency control"""
        if not self.active_clients:
            return {"success": 0, "failed": 0, "total": 0}
        
        semaphore = asyncio.Semaphore(3)
        results = {"success": 0, "failed": 0, "total": len(self.active_clients)}
        
        async def report_one(client_data):
            async with semaphore:
                client = client_data["client"]
                try:
                    await client.report_chat(
                        chat_id=target_chat,
                        reason=reason,
                        message_ids=[],
                        description=description[:500]  # Telegram limit
                    )
                    return True
                except FloodWait as e:
                    await asyncio.sleep(e.value)
                    return False
                except:
                    return False
        
        tasks = [report_one(c) for c in self.active_clients]
        task_results = await asyncio.gather(*tasks)
        
        results["success"] = sum(task_results)
        results["failed"] = len(task_results) - results["success"]
        
        return results

reporter = MassReporter()
validator = SessionValidator()
