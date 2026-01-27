import asyncio
import logging
from typing import Any

from pyrogram import Client
from pyrogram.errors import PeerIdInvalid, UsernameInvalid, UsernameNotOccupied

logger = logging.getLogger(__name__)

_peer_cache: dict[str, Any] = {}
_invalid_cache: set[str] = set()
_inflight_locks: dict[str, asyncio.Lock] = {}
_cache_lock = asyncio.Lock()


def _normalize_target(raw_target: str) -> str:
    cleaned = raw_target.strip()
    if not cleaned:
        return ""
    if cleaned.startswith("https://"):
        cleaned = cleaned[len("https://"):]
    elif cleaned.startswith("http://"):
        cleaned = cleaned[len("http://"):]
    cleaned = cleaned.replace("www.", "", 1)
    for prefix in ("t.me/", "telegram.me/"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
    return cleaned.strip()


def _detect_target_type(cleaned: str) -> tuple[str, str | int]:
    invite_prefixes = ("joinchat/", "+")
    for prefix in invite_prefixes:
        if cleaned.startswith(prefix):
            invite_hash = cleaned[len(prefix):]
            if prefix == "+":
                return "invite", f"https://t.me/+{invite_hash}"
            return "invite", f"https://t.me/joinchat/{invite_hash}"

    if "/joinchat/" in cleaned:
        invite_hash = cleaned.split("/joinchat/")[-1]
        return "invite", f"https://t.me/joinchat/{invite_hash}"
    if "/+" in cleaned:
        invite_hash = cleaned.split("/+", 1)[-1]
        return "invite", f"https://t.me/+{invite_hash}"

    trimmed = cleaned.lstrip("@")
    if trimmed.lstrip("-").isdigit():
        return "id", int(trimmed)

    return "username", trimmed


async def _get_lock(key: str) -> asyncio.Lock:
    async with _cache_lock:
        if key not in _inflight_locks:
            _inflight_locks[key] = asyncio.Lock()
        return _inflight_locks[key]


async def resolve_target_peer(
    client: Client,
    target: str | int,
    *,
    log: logging.Logger | None = None,
    retry_delay: float = 1.0,
):
    logger_to_use = log or logger
    original_input = str(target)
    normalized = _normalize_target(original_input)
    if not normalized:
        logger_to_use.warning("Resolve failed: empty target input=%s", original_input)
        return None

    target_type, lookup_value = _detect_target_type(normalized)
    cache_key = f"{target_type}:{lookup_value}"

    async with _cache_lock:
        if cache_key in _peer_cache:
            cached = _peer_cache[cache_key]
            logger_to_use.info(
                "Resolve cache hit: input=%s type=%s id=%s",
                original_input,
                target_type,
                getattr(cached, "id", None),
            )
            return cached
        if cache_key in _invalid_cache:
            logger_to_use.warning(
                "Resolve cached invalid: input=%s type=%s",
                original_input,
                target_type,
            )
            return None

    lock = await _get_lock(cache_key)
    async with lock:
        async with _cache_lock:
            if cache_key in _peer_cache:
                return _peer_cache[cache_key]
            if cache_key in _invalid_cache:
                return None

        for attempt in range(2):
            try:
                if target_type == "invite":
                    entity = await client.get_chat(lookup_value)
                elif target_type == "id":
                    if isinstance(lookup_value, int) and lookup_value > 0:
                        entity = await client.get_users(lookup_value)
                    else:
                        entity = await client.get_chat(lookup_value)
                else:
                    entity = await client.get_chat(lookup_value)

                resolved_id = getattr(entity, "id", None)
                if resolved_id is None:
                    raise ValueError("Resolved entity missing id")

                async with _cache_lock:
                    _peer_cache[cache_key] = entity

                logger_to_use.info(
                    "Resolved target: input=%s normalized=%s type=%s id=%s",
                    original_input,
                    normalized,
                    target_type,
                    resolved_id,
                )
                return entity
            except (PeerIdInvalid, UsernameInvalid, UsernameNotOccupied) as error:
                logger_to_use.warning(
                    "Resolve failed: input=%s normalized=%s type=%s error=%s",
                    original_input,
                    normalized,
                    target_type,
                    error.__class__.__name__,
                )
            except Exception as error:
                logger_to_use.warning(
                    "Resolve failed: input=%s normalized=%s type=%s error=%s",
                    original_input,
                    normalized,
                    target_type,
                    str(error)[:120],
                )

            if attempt == 0:
                await asyncio.sleep(retry_delay)

        async with _cache_lock:
            _invalid_cache.add(cache_key)
        return None
