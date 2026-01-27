from __future__ import annotations

from typing import Any


def normalize_target(raw: str | int) -> dict[str, Any]:
    raw_input = raw
    if isinstance(raw, int):
        return {
            "raw_input": raw_input,
            "kind": "id",
            "normalized_value": int(raw),
        }

    cleaned = str(raw).strip()
    if not cleaned:
        raise ValueError("Empty target input")

    cleaned = cleaned.replace("https://", "").replace("http://", "")
    if cleaned.startswith("www."):
        cleaned = cleaned[len("www.") :]

    if cleaned.startswith("@"):
        username = cleaned.lstrip("@").strip()
        return {
            "raw_input": raw_input,
            "kind": "username",
            "normalized_value": username,
        }

    link_fragment = None
    for prefix in ("t.me/", "telegram.me/"):
        if prefix in cleaned:
            link_fragment = cleaned.split(prefix, 1)[1].strip("/")
            break

    if link_fragment:
        if link_fragment.startswith("+") or link_fragment.startswith("joinchat/"):
            normalized_link = f"https://t.me/{link_fragment}"
            return {
                "raw_input": raw_input,
                "kind": "invite_link",
                "normalized_value": normalized_link,
            }
        username = link_fragment.split("/", 1)[0].lstrip("@").strip()
        return {
            "raw_input": raw_input,
            "kind": "public_link",
            "normalized_value": username,
        }

    trimmed = cleaned.strip()
    if trimmed.lstrip("-").isdigit():
        return {
            "raw_input": raw_input,
            "kind": "id",
            "normalized_value": int(trimmed),
        }

    return {
        "raw_input": raw_input,
        "kind": "username",
        "normalized_value": trimmed.lstrip("@").strip(),
    }
