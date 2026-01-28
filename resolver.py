from __future__ import annotations

import logging
from typing import Any

from pyrogram import Client
from pyrogram.errors import (
    ChannelPrivate,
    ChatAdminRequired,
    FloodWait,
    InviteHashExpired,
    InviteHashInvalid,
    PeerIdInvalid,
    RPCError,
    UserNotParticipant,
    UsernameInvalid,
    UsernameNotOccupied,
)

from cache_helper import TTLCache
from normalize import normalize_target
from sessions import client_peer_cache

logger = logging.getLogger(__name__)

_RESOLVED_TTL = 5 * 60
_NOT_MEMBER_TTL = 30
_INVALID_TTL = 10 * 60

_resolved_cache = TTLCache()
_not_member_cache = TTLCache()
_invalid_cache = TTLCache()


def _get_alias(client: Client) -> str:
    return getattr(client, "alias", getattr(client, "name", "unknown"))


def _get_cached_peer(alias: str, chat_id: int) -> Any | None:
    return client_peer_cache.get(alias, {}).get(chat_id)


def _cache_key(alias: str, key: str) -> tuple[str, str]:
    return alias, key


def _not_member_key(alias: str, chat_id: int) -> tuple[str, str]:
    return alias, f"chat:{chat_id}"


async def resolve_target(client: Client, target: str | int) -> dict[str, Any]:
    alias = _get_alias(client)
    try:
        normalized = normalize_target(target)
    except ValueError as error:
        logger.info(
            "[BLOCKED] alias=%s target=%s reason=INVALID error=%s",
            alias,
            target,
            str(error)[:120],
        )
        return {
            "ok": False,
            "chat_id": None,
            "title": None,
            "reason": "INVALID",
            "error": str(error)[:120],
        }

    key = normalized["normalized_key"]
    cached_invalid, invalid_ttl = _invalid_cache.get_with_ttl(_cache_key(alias, key))
    if cached_invalid:
        if invalid_ttl is not None:
            logger.debug(
                "Resolve cached invalid alias=%s target=%s ttl=%.1fs",
                alias,
                normalized["raw_input"],
                invalid_ttl,
            )
        logger.info(
            "[BLOCKED] alias=%s target=%s reason=%s error=cached",
            alias,
            normalized["raw_input"],
            cached_invalid["reason"],
        )
        return {
            "ok": False,
            "chat_id": None,
            "title": None,
            "reason": cached_invalid["reason"],
            "error": "cached",
        }

    cached_resolved, resolved_ttl = _resolved_cache.get_with_ttl(_cache_key(alias, key))
    if cached_resolved:
        if resolved_ttl is not None:
            logger.debug(
                "Resolve cached ok alias=%s target=%s ttl=%.1fs",
                alias,
                normalized["raw_input"],
                resolved_ttl,
            )
        chat_id = cached_resolved["chat_id"]
        title = cached_resolved.get("title")
        cached_not_member, not_member_ttl = _not_member_cache.get_with_ttl(
            _not_member_key(alias, chat_id),
        )
        if cached_not_member:
            if not_member_ttl is not None:
                logger.debug(
                    "Resolve cached not_member alias=%s target=%s ttl=%.1fs",
                    alias,
                    normalized["raw_input"],
                    not_member_ttl,
                )
            logger.info(
                "[ACCESS] alias=%s target=%s chat_id=%s title=%s",
                alias,
                normalized["raw_input"],
                chat_id,
                title,
            )
            logger.info(
                "[BLOCKED] alias=%s target=%s chat_id=%s reason=NOT_A_MEMBER error=cached",
                alias,
                normalized["raw_input"],
                chat_id,
            )
            return {
                "ok": False,
                "chat_id": chat_id,
                "title": title,
                "reason": "NOT_A_MEMBER",
                "error": "cached",
            }
        logger.info(
            "[ACCESS] alias=%s target=%s chat_id=%s title=%s",
            alias,
            normalized["raw_input"],
            chat_id,
            title,
        )
        return {
            "ok": True,
            "chat_id": chat_id,
            "title": title,
            "reason": None,
            "error": None,
        }

    kind = normalized["kind"]
    value = normalized["normalized_value"]

    try:
        if kind == "id":
            chat_id = int(value)
            cached_peer = _get_cached_peer(alias, chat_id)
            if cached_peer:
                entity = cached_peer
            else:
                entity = await client.get_chat(chat_id)
        elif kind in {"username", "public_link"}:
            entity = await client.get_chat(str(value))
        elif kind == "invite_link":
            entity = await client.get_chat(str(value))
        else:
            raise ValueError(f"Unsupported kind: {kind}")
    except (InviteHashInvalid, InviteHashExpired):
        _invalid_cache.set(
            _cache_key(alias, key),
            {"reason": "INVALID"},
            _INVALID_TTL,
        )
        logger.info(
            "[BLOCKED] alias=%s target=%s reason=INVALID error=invite_invalid",
            alias,
            normalized["raw_input"],
        )
        return {
            "ok": False,
            "chat_id": None,
            "title": None,
            "reason": "INVALID",
            "error": "invite_invalid",
        }
    except (UsernameInvalid, UsernameNotOccupied, PeerIdInvalid, ValueError) as error:
        _invalid_cache.set(
            _cache_key(alias, key),
            {"reason": "INVALID"},
            _INVALID_TTL,
        )
        logger.info(
            "[BLOCKED] alias=%s target=%s reason=INVALID error=%s",
            alias,
            normalized["raw_input"],
            error.__class__.__name__,
        )
        return {
            "ok": False,
            "chat_id": None,
            "title": None,
            "reason": "INVALID",
            "error": error.__class__.__name__,
        }
    except (ChannelPrivate, ChatAdminRequired) as error:
        logger.info(
            "[BLOCKED] alias=%s target=%s reason=PRIVATE error=%s",
            alias,
            normalized["raw_input"],
            error.__class__.__name__,
        )
        return {
            "ok": False,
            "chat_id": None,
            "title": None,
            "reason": "PRIVATE",
            "error": error.__class__.__name__,
        }
    except FloodWait as error:
        logger.info(
            "[BLOCKED] alias=%s target=%s reason=FLOODWAIT error=%ss",
            alias,
            normalized["raw_input"],
            error.value,
        )
        return {
            "ok": False,
            "chat_id": None,
            "title": None,
            "reason": "FLOODWAIT",
            "error": str(error.value),
        }
    except RPCError as error:
        logger.info(
            "[BLOCKED] alias=%s target=%s reason=RPC_ERROR error=%s",
            alias,
            normalized["raw_input"],
            error.__class__.__name__,
        )
        return {
            "ok": False,
            "chat_id": None,
            "title": None,
            "reason": "RPC_ERROR",
            "error": error.__class__.__name__,
        }
    except Exception as error:
        logger.info(
            "[BLOCKED] alias=%s target=%s reason=RPC_ERROR error=%s",
            alias,
            normalized["raw_input"],
            str(error)[:120],
        )
        return {
            "ok": False,
            "chat_id": None,
            "title": None,
            "reason": "RPC_ERROR",
            "error": str(error)[:120],
        }

    chat_id = getattr(entity, "id", None)
    title = getattr(entity, "title", None)
    if chat_id is None:
        logger.info(
            "[BLOCKED] alias=%s target=%s reason=RPC_ERROR error=missing_chat_id",
            alias,
            normalized["raw_input"],
        )
        return {
            "ok": False,
            "chat_id": None,
            "title": None,
            "reason": "RPC_ERROR",
            "error": "missing_chat_id",
        }

    me = await client.get_me()
    logger.info(
        "[ACCESS] alias=%s me=%s target=%s chat_id=%s title=%s",
        alias,
        me.id,
        normalized["raw_input"],
        chat_id,
        title,
    )
    try:
        await client.get_chat_member(chat_id, me.id)
    except UserNotParticipant:
        _not_member_cache.set(
            _not_member_key(alias, chat_id),
            {"reason": "NOT_A_MEMBER"},
            _NOT_MEMBER_TTL,
        )
        logger.info(
            "[BLOCKED] alias=%s me=%s target=%s chat_id=%s reason=NOT_A_MEMBER error=not_member",
            alias,
            me.id,
            normalized["raw_input"],
            chat_id,
        )
        return {
            "ok": False,
            "chat_id": chat_id,
            "title": title,
            "reason": "NOT_A_MEMBER",
            "error": None,
        }
    except (ChannelPrivate, ChatAdminRequired) as error:
        logger.info(
            "[BLOCKED] alias=%s me=%s target=%s chat_id=%s reason=PRIVATE error=%s",
            alias,
            me.id,
            normalized["raw_input"],
            chat_id,
            error.__class__.__name__,
        )
        return {
            "ok": False,
            "chat_id": chat_id,
            "title": title,
            "reason": "PRIVATE",
            "error": error.__class__.__name__,
        }
    except FloodWait as error:
        logger.info(
            "[BLOCKED] alias=%s me=%s target=%s chat_id=%s reason=FLOODWAIT error=%ss",
            alias,
            me.id,
            normalized["raw_input"],
            chat_id,
            error.value,
        )
        return {
            "ok": False,
            "chat_id": chat_id,
            "title": title,
            "reason": "FLOODWAIT",
            "error": str(error.value),
        }
    except RPCError as error:
        logger.info(
            "[BLOCKED] alias=%s me=%s target=%s chat_id=%s reason=RPC_ERROR error=%s",
            alias,
            me.id,
            normalized["raw_input"],
            chat_id,
            error.__class__.__name__,
        )
        return {
            "ok": False,
            "chat_id": chat_id,
            "title": title,
            "reason": "RPC_ERROR",
            "error": error.__class__.__name__,
        }
    except Exception as error:
        logger.info(
            "[BLOCKED] alias=%s me=%s target=%s chat_id=%s reason=RPC_ERROR error=%s",
            alias,
            me.id,
            normalized["raw_input"],
            chat_id,
            str(error)[:120],
        )
        return {
            "ok": False,
            "chat_id": chat_id,
            "title": title,
            "reason": "RPC_ERROR",
            "error": str(error)[:120],
        }

    _resolved_cache.set(
        _cache_key(alias, key),
        {"chat_id": chat_id, "title": title},
        _RESOLVED_TTL,
    )
    return {
        "ok": True,
        "chat_id": chat_id,
        "title": title,
        "reason": None,
        "error": None,
    }


async def ensure_target_ready(
    client: Client,
    alias: str,
    raw_target: str | int,
) -> dict[str, Any]:
    _ = alias
    result = await resolve_target(client, raw_target)
    if not result["ok"]:
        return {
            "ok": False,
            "normalized": normalize_target(raw_target),
            "reason": result["reason"],
            "error": result.get("error"),
        }

    chat_id = result["chat_id"]
    entity = None
    if chat_id is not None:
        cached_entity = _get_cached_peer(alias, chat_id)
        if cached_entity:
            entity = cached_entity
        else:
            entity = await client.get_chat(chat_id)
    return {
        "ok": True,
        "entity": entity,
        "chat_id": chat_id,
        "chat_type": str(getattr(entity, "type", None)),
        "normalized": normalize_target(raw_target),
    }
