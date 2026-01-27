from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from pyrogram import Client

from config import API_HASH, API_ID
from database import db

logger = logging.getLogger(__name__)


def _unique_client_name(alias: str) -> str:
    short_uuid = uuid.uuid4().hex[:8]
    safe_alias = alias.replace(" ", "_")
    return f"user_{safe_alias}_{short_uuid}"


async def detect_collisions(client_records: list[dict[str, Any]]) -> None:
    seen: dict[int, str] = {}
    for record in client_records:
        me = record.get("me")
        alias = record.get("alias")
        if not me:
            continue
        if me.id in seen:
            logger.error(
                "SESSION COLLISION: alias=%s collides_with=%s account_id=%s",
                alias,
                seen[me.id],
                me.id,
            )
            raise RuntimeError(
                "SESSION COLLISION: multiple clients logged in as same account"
            )
        seen[me.id] = alias


async def _start_client(session: dict[str, Any]) -> dict[str, Any] | None:
    session_name = session.get("session_name") or str(session.get("_id", "unknown"))
    session_string = session.get("session_string")
    if not session_string:
        logger.warning("Session %s missing session_string; skipping.", session_name)
        return None
    client_name = _unique_client_name(session_name)
    client = Client(
        client_name,
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=session_string,
        in_memory=True,
        no_updates=True,
    )
    await client.start()
    me = await client.get_me()
    client.alias = session_name
    client.client_name = client_name
    logger.info(
        "Session started: alias=%s client_name=%s me_id=%s is_bot=%s phone=%s",
        session_name,
        client_name,
        me.id,
        me.is_bot,
        getattr(me, "phone_number", None),
    )
    return {"alias": session_name, "client": client, "me": me, "session": session}


async def build_clients(
    sessions: list[dict[str, Any]] | None = None,
    concurrency: int = 5,
) -> list[dict[str, Any]]:
    if not (API_ID and API_HASH and API_ID != 0):
        logger.error("Missing API_ID/API_HASH. Cannot build clients.")
        return []

    session_docs = sessions if sessions is not None else await db.get_all_sessions()
    semaphore = asyncio.Semaphore(concurrency)

    async def run_one(session: dict[str, Any]):
        async with semaphore:
            try:
                return await _start_client(session)
            except Exception as error:
                session_name = session.get("session_name") or str(session.get("_id", "unknown"))
                logger.warning("Failed to start session %s: %s", session_name, str(error)[:120])
                return None

    tasks = [run_one(session) for session in session_docs]
    results = await asyncio.gather(*tasks)
    clients = [result for result in results if result]
    await detect_collisions(clients)
    return clients
