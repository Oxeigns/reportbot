import asyncio
import logging
import types
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
        self.per_report_delay = 1.5
        self.between_clients_delay = 1.0
        self.between_attempts_delay = 2.0
        self.retry_delay = 2.0
        self.floodwait_buffer = 2
        self.max_retries = 1

    async def _report_with_retries(self, report_call, client_name: str) -> bool:
        for attempt in range(self.max_retries + 1):
            try:
                await report_call()
                await asyncio.sleep(self.per_report_delay)
                return True
            except FloodWait as error:
                wait_time = error.value + self.floodwait_buffer
                logger.warning("FloodWait for %s: %ss", client_name, wait_time)
                await asyncio.sleep(wait_time)
            except Exception as error:
                logger.warning("Report failed for %s: %s", client_name, str(error)[:120])
                await asyncio.sleep(self.retry_delay)
        return False
    
    @staticmethod
    async def _ensure_peer(client: Client, target_chat):
        try:
            await client.resolve_peer(target_chat)
            return
        except Exception as first_error:
            try:
                await client.get_chat(target_chat)
            except Exception as second_error:
                raise second_error from first_error
        await client.resolve_peer(target_chat)

    @staticmethod
    def _attach_report_helpers(client: Client) -> None:
        if not hasattr(client, "report_message"):
            async def report_message(self, target_chat, message_ids, reason, description: str = ""):
                await MassReporter._ensure_peer(self, target_chat)
                await self.invoke(
                    raw.functions.messages.Report(
                        peer=await self.resolve_peer(target_chat),
                        reason=reason,
                        message=description or "",
                        id=message_ids
                    )
                )

            client.report_message = types.MethodType(report_message, client)

        if not hasattr(client, "report_chat"):
            async def report_chat(self, target_chat, reason, description: str = ""):
                await MassReporter._ensure_peer(self, target_chat)
                await self.invoke(
                    raw.functions.messages.Report(
                        peer=await self.resolve_peer(target_chat),
                        reason=reason,
                        message=description or "",
                        id=[]
                    )
                )

            client.report_chat = types.MethodType(report_chat, client)

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
                self._attach_report_helpers(client)
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
        attempts: int = 1,
        on_progress=None
    ) -> dict:
        """🔥 Mass report"""
        if not self.active_clients:
            return {"success": 0, "failed": 0, "total": 0}

        clients = list(self.active_clients)
        return await self._run_global_attempts(
            clients=clients,
            total_attempts=attempts,
            report_factory=lambda client: lambda: client.report_chat(
                target_chat,
                reason,
                description=description
            ),
            on_progress=on_progress
        )

    async def mass_report_message(
        self,
        target_chat: str,
        message_ids: list[int],
        reason,
        description: str = "",
        attempts: int = 1,
        on_progress=None
    ) -> dict:
        """🔥 Mass report specific messages"""
        if not self.active_clients:
            return {"success": 0, "failed": 0, "total": 0}

        if not message_ids:
            return {"success": 0, "failed": 0, "total": 0}

        clients = list(self.active_clients)
        return await self._run_global_attempts(
            clients=clients,
            total_attempts=attempts,
            report_factory=lambda client: lambda: client.report_message(
                target_chat,
                message_ids,
                reason,
                description=description
            ),
            on_progress=on_progress
        )

    async def _run_global_attempts(
        self,
        clients: list[dict],
        total_attempts: int,
        report_factory,
        on_progress=None
    ) -> dict:
        if total_attempts < 1 or not clients:
            return {"success": 0, "failed": 0, "total": 0, "attempt_success": 0, "attempt_failed": 0}

        results = {
            "success": 0,
            "failed": 0,
            "total": 0,
            "attempt_success": 0,
            "attempt_failed": 0
        }
        completed_attempts = 0
        lock = asyncio.Lock()
        client_index = 0

        while completed_attempts < total_attempts:
            client_data = clients[client_index % len(clients)]
            client_index += 1

            async with lock:
                if completed_attempts >= total_attempts:
                    break
                current_attempt = completed_attempts + 1
                remaining = total_attempts - current_attempt

            logger.info(
                "Reporting with %s (attempt %s/%s, remaining %s)",
                client_data["name"],
                current_attempt,
                total_attempts,
                remaining
            )

            client = client_data["client"]
            report_call = report_factory(client)
            ok = await self._report_with_retries(report_call, client_data["name"])

            async with lock:
                completed_attempts += 1
                if ok:
                    results["success"] += 1
                    results["attempt_success"] += 1
                else:
                    results["failed"] += 1
                    results["attempt_failed"] += 1
                results["total"] += 1

            if on_progress:
                await on_progress(completed_attempts, total_attempts, results)

            await asyncio.sleep(self.between_clients_delay)
            if completed_attempts < total_attempts and client_index % len(clients) == 0:
                await asyncio.sleep(self.between_attempts_delay)

        return results

reporter = MassReporter()
