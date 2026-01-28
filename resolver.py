from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from pyrogram import Client
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import (
    ChannelPrivate,
    ChatAdminRequired,
    InviteHashExpired,
    InviteHashInvalid,
    PeerIdInvalid,
    RPCError,
    UserNotParticipant,
)

from normalize import normalize_target

logger = logging.getLogger(__name__)

_RESOLVED_TTL = 30 * 60
_INVALID_TTL = 10 * 60

_resolved_cache: dict[tuple[str, str], dict[str, Any]] = {}
_invalid_cache: dict[tuple[str, str], dict[str, Any]] = {}


@dataclass
class ResolveError(Exception):
    code: str
    details: str


def _now() -> float:
    return time.monotonic()


def _normalized_key(normalized: dict[str, Any]) -> str:
    return f"{normalized['kind']}:{normalized['normalized_value']}"


def _get_alias(client: Client) -> str:
    return getattr(client, "alias", getattr(client, "name", "unknown"))


def _cache_expired(entry: dict[str, Any]) -> bool:
    return entry.get("expires_at", 0) <= _now()


def _set_resolved(alias: str, key: str, entity_id: int) -> None:
    _resolved_cache[(alias, key)] = {
        "entity_id": entity_id,
        "expires_at": _now() + _RESOLVED_TTL,
    }


def _set_invalid(alias: str, key: str, error_code: str) -> None:
    _invalid_cache[(alias, key)] = {
        "error_code": error_code,
        "expires_at": _now() + _INVALID_TTL,
    }


def _get_cached_resolved(alias: str, key: str) -> dict[str, Any] | None:
    entry = _resolved_cache.get((alias, key))
    if not entry:
        return None
    if _cache_expired(entry):
        _resolved_cache.pop((alias, key), None)
        return None
    return entry


def _get_cached_invalid(alias: str, key: str) -> dict[str, Any] | None:
    entry = _invalid_cache.get((alias, key))
    if not entry:
        return None
    if _cache_expired(entry):
        _invalid_cache.pop((alias, key), None)
        return None
    return entry


async def resolve_entity(
    client: Client,
    normalized: dict[str, Any],
) -> tuple[Any, int, str]:
    kind = normalized["kind"]
    value = normalized["normalized_value"]

    try:
        if kind == "id":
            entity = await client.get_chat(int(value))
        elif kind in {"username", "public_link"}:
            entity = await client.get_chat(str(value))
        elif kind == "invite_link":
            try:
                entity = await client.get_chat(str(value))
            except (InviteHashInvalid, InviteHashExpired) as error:
                raise ResolveError(
                    "INVITE_LINK_NOT_RESOLVABLE",
                    f"invite invalid: {error.__class__.__name__}",
                )
            except (PeerIdInvalid, ChannelPrivate, ChatAdminRequired) as error:
                raise ResolveError(
                    "INVITE_LINK_NOT_RESOLVABLE",
                    f"invite not accessible: {error.__class__.__name__}",
                )
            except RPCError as error:
                raise ResolveError(
                    "INVITE_LINK_NOT_RESOLVABLE",
                    f"invite requires join: {error.__class__.__name__}",
                )
        else:
            raise ResolveError("INVALID_TARGET", f"Unsupported kind: {kind}")
    except ResolveError:
        raise
    except PeerIdInvalid as error:
        raise ResolveError("PEER_ID_INVALID", str(error))
    except RPCError as error:
        raise ResolveError("RESOLVE_RPC_ERROR", str(error))
    except Exception as error:
        raise ResolveError("RESOLVE_FAILED", str(error))

    chat_id = getattr(entity, "id", None)
    if chat_id is None:
        raise ResolveError("RESOLVE_FAILED", "Resolved entity missing id")
    chat_type = getattr(entity, "type", None)
    return entity, chat_id, str(chat_type)


async def verify_access(client: Client, entity: Any) -> dict[str, Any]:
    alias = _get_alias(client)
    me = await client.get_me()
    member = None
    member_status = None
    for attempt in range(2):
        try:
            member = await client.get_chat_member(entity.id, "me")
            member_status = getattr(member, "status", None)
            break
        except UserNotParticipant:
            return {
                "ok": False,
                "reason": "NOT_A_MEMBER",
                "member_status": None,
                "me_id": me.id,
            }
        except (ChannelPrivate, ChatAdminRequired, PeerIdInvalid) as error:
            return {
                "ok": False,
                "reason": error.__class__.__name__.upper(),
                "member_status": None,
                "me_id": me.id,
            }
        except RPCError as error:
            if attempt == 0:
                logger.warning(
                    "Access check RPC error alias=%s me=%s target=%s err=%s retrying",
                    alias,
                    me.id,
                    getattr(entity, "id", None),
                    error.__class__.__name__,
                )
                continue
            return {
                "ok": False,
                "reason": "RPC_ERROR",
                "member_status": None,
                "me_id": me.id,
            }
        except Exception as error:
            return {
                "ok": False,
                "reason": "UNKNOWN_ERROR",
                "member_status": None,
                "me_id": me.id,
                "error": str(error)[:120],
            }

    ok_statuses = {
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER,
    }
    if member_status in ok_statuses:
        return {
            "ok": True,
            "reason": "ACCESS_OK",
            "member_status": member_status,
            "me_id": me.id,
        }

    return {
        "ok": False,
        "reason": "NO_ACCESS",
        "member_status": member_status,
        "me_id": me.id,
    }


async def ensure_target_ready(client: Client, raw_target: str | int) -> dict[str, Any]:
    alias = _get_alias(client)
    normalized = normalize_target(raw_target)
    key = _normalized_key(normalized)

    cached_invalid = _get_cached_invalid(alias, key)
    if cached_invalid:
        me_id = None
        try:
            me_id = (await client.get_me()).id
        except Exception:
            me_id = None
        logger.info(
            "[BLOCKED] alias=%s me=%s target=%s reason=%s error=%s",
            alias,
            me_id,
            normalized["raw_input"],
            cached_invalid["error_code"],
            "cached",
        )
        return {
            "ok": False,
            "normalized": normalized,
            "reason": cached_invalid["error_code"],
        }

    cached_resolved = _get_cached_resolved(alias, key)
    if cached_resolved:
        try:
            entity = await client.get_chat(cached_resolved["entity_id"])
            chat_id = entity.id
            chat_type = str(getattr(entity, "type", None))
        except Exception:
            _resolved_cache.pop((alias, key), None)
            cached_resolved = None

    if not cached_resolved:
        try:
            entity, chat_id, chat_type = await resolve_entity(client, normalized)
            _set_resolved(alias, key, chat_id)
        except ResolveError as error:
            _set_invalid(alias, key, error.code)
            me_id = None
            try:
                me_id = (await client.get_me()).id
            except Exception:
                me_id = None
            logger.info(
                "[BLOCKED] alias=%s me=%s target=%s reason=%s error=%s",
                alias,
                me_id,
                normalized["raw_input"],
                error.code,
                error.details,
            )
            return {
                "ok": False,
                "normalized": normalized,
                "reason": error.code,
                "error": error.details,
            }

    access = await verify_access(client, entity)
    if access["ok"]:
        logger.info(
            "[READY] alias=%s me=%s target=%s chat_id=%s type=%s title=%s status=%s",
            alias,
            access["me_id"],
            normalized["raw_input"],
            chat_id,
            chat_type,
            getattr(entity, "title", None),
            access.get("member_status"),
        )
        return {
            "ok": True,
            "entity": entity,
            "chat_id": chat_id,
            "chat_type": chat_type,
            "normalized": normalized,
        }

    _set_invalid(alias, key, access["reason"])
    logger.info(
        "[BLOCKED] alias=%s me=%s target=%s chat_id=%s type=%s title=%s reason=%s error=%s",
        alias,
        access.get("me_id"),
        normalized["raw_input"],
        chat_id,
        chat_type,
        getattr(entity, "title", None),
        access["reason"],
        access.get("member_status"),
    )
    return {
        "ok": False,
        "normalized": normalized,
        "reason": access["reason"],
        "member_status": access.get("member_status"),
    }
