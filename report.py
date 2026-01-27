import asyncio
import logging
from pyrogram import Client, raw
from pyrogram.errors import FloodWait
from config import API_ID, API_HASH
from database import db

logger = logging.getLogger(__name__)

class SessionValidator:
    @staticmethod
    async def test_session(session_string: str, session_name: str) -> tuple[bool, str]:
        """🔥 ROBUST session testing - CATCHES ALL ERRORS"""
        try:
            if not (API_ID and API_HASH and API_ID != 0):
                return False, "❌ Missing API_ID/API_HASH in config"
            client = Client(
                session_name,
                api_id=API_ID,
                api_hash=API_HASH,
                session_string=session_string,
                in_memory=True,
                no_updates=True
            )
            
            await client.start()
            me = await client.get_me()
            await client.stop()
            
            return True, f"✅ {me.first_name}"
            
        except FloodWait as e:
            return False, f"⏳ FloodWait {e.value}s"
        except Exception as e:
            # 🔥 CATCHES "Incorrect padding" + ALL OTHER ERRORS
            error_msg = str(e).lower()
            if "padding" in error_msg or "authkey" in error_msg:
                return False, "❌ **Invalid session** - REGENERATE"
            return False, f"❌ {str(e)[:50]}"

class MassReporter:
    def __init__(self):
        self.active_clients = []

    def has_api_credentials(self) -> bool:
        return bool(API_ID and API_HASH and API_ID != 0)

    async def validate_all_sessions(self) -> dict:
        """🔥 VALIDATE ALL sessions"""
        if not self.has_api_credentials():
            logger.error("Missing API_ID/API_HASH. Cannot validate sessions.")
            return {"active": 0, "failed": 0, "total": 0}
        pending = await db.get_pending_sessions()
        failed = await db.get_failed_sessions()
        all_to_validate = failed + pending
        
        results = {"active": 0, "failed": 0, "total": len(all_to_validate)}
        
        for session in all_to_validate:
            session_name = session.get("session_name")
            if not session_name:
                session_name = await db.ensure_session_name(session)
                if not session_name:
                    logger.warning("Session missing session_name and _id; skipping validation.")
                    results["total"] -= 1
                    continue
            session_string = session.get("session_string")
            if not session_string:
                logger.warning("Session %s missing session_string; marking failed.", session_name)
                await db.update_session_status(session_name, "failed", "❌ Missing session_string")
                results["failed"] += 1
                continue
            
            success, message = await SessionValidator.test_session(session_string, session_name)
            status = "active" if success else "failed"
            
            await db.update_session_status(session_name, status, message if not success else None)
            
            if success:
                results["active"] += 1
            else:
                results["failed"] += 1
        
        return results

    async def load_active_clients(self) -> int:
        """Load active sessions"""
        if not self.has_api_credentials():
            logger.error("Missing API_ID/API_HASH. Cannot load sessions.")
            return 0
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
            except Exception as error:
                await db.update_session_status(
                    session["session_name"],
                    "failed",
                    f"❌ {str(error)[:80]}"
                )
                continue
        
        return len(self.active_clients)

    async def join_target_chat(self, chat_link: str) -> int:
        """Join target"""
        joined = 0
        semaphore = asyncio.Semaphore(2)
        
        async def join_one(client_data):
            async with semaphore:
                try:
                    await client_data["client"].join_chat(chat_link)
                    return True
                except:
                    return False
        
        if not self.active_clients:
            return 0
            
        tasks = [join_one(c) for c in self.active_clients]
        results = await asyncio.gather(*tasks)
        return sum(results)

    async def mass_report_chat(
        self,
        target_chat: str,
        reason,
        description: str = "",
        max_reports: int | None = None,
        retries: int = 1
    ) -> dict:
        """🔥 Mass report"""
        if not self.active_clients:
            return {"success": 0, "failed": 0, "total": 0}

        clients = list(self.active_clients)
        if max_reports is not None:
            clients = clients[:max_reports]

        results = {"success": 0, "failed": 0, "total": len(clients)}
        
        async def report_one(client_data):
            client = client_data["client"]
            try:
                await client.invoke(
                    raw.functions.messages.Report(
                        peer=await client.resolve_peer(target_chat),
                        reason=reason,
                        message=description or "",
                        id=[],
                        option=b""
                    )
                )
                await asyncio.sleep(1)
                return True
            except FloodWait as e:
                await asyncio.sleep(e.value + 1)
                return False
            except:
                return False

        remaining_clients = clients
        for attempt in range(retries + 1):
            if not remaining_clients:
                break
            tasks = [report_one(c) for c in remaining_clients]
            task_results = await asyncio.gather(*tasks, return_exceptions=True)
            next_remaining = []

            for client_data, result in zip(remaining_clients, task_results):
                if result is True:
                    results["success"] += 1
                else:
                    next_remaining.append(client_data)

            remaining_clients = next_remaining
            if attempt < retries and remaining_clients:
                await asyncio.sleep(1)

        results["failed"] = len(remaining_clients)

        return results

    async def mass_report_message(
        self,
        target_chat: str,
        message_ids: list[int],
        reason,
        description: str = "",
        max_reports: int | None = None,
        retries: int = 1
    ) -> dict:
        """🔥 Mass report specific messages"""
        if not self.active_clients:
            return {"success": 0, "failed": 0, "total": 0}

        if not message_ids:
            return {"success": 0, "failed": 0, "total": 0}

        clients = list(self.active_clients)
        if max_reports is not None:
            clients = clients[:max_reports]

        results = {"success": 0, "failed": 0, "total": len(clients)}

        async def report_one(client_data):
            client = client_data["client"]
            try:
                await client.invoke(
                    raw.functions.messages.Report(
                        peer=await client.resolve_peer(target_chat),
                        reason=reason,
                        message=description or "",
                        id=message_ids,
                        option=b""
                    )
                )
                await asyncio.sleep(1)
                return True
            except FloodWait as e:
                await asyncio.sleep(e.value + 1)
                return False
            except:
                return False

        remaining_clients = clients
        for attempt in range(retries + 1):
            if not remaining_clients:
                break
            tasks = [report_one(c) for c in remaining_clients]
            task_results = await asyncio.gather(*tasks, return_exceptions=True)
            next_remaining = []

            for client_data, result in zip(remaining_clients, task_results):
                if result is True:
                    results["success"] += 1
                else:
                    next_remaining.append(client_data)

            remaining_clients = next_remaining
            if attempt < retries and remaining_clients:
                await asyncio.sleep(1)

        results["failed"] = len(remaining_clients)

        return results

reporter = MassReporter()
