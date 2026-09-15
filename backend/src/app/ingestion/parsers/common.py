"""Shared, pure parsing helpers used by all three source parsers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.ingestion.types import NormalizedAcl


def require_str(record: dict[str, Any], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"missing or invalid required field '{field}'")
    return value


def require_datetime(record: dict[str, Any], field: str) -> datetime:
    value = record.get(field)
    if not isinstance(value, str):
        raise ValueError(f"missing or invalid required field '{field}'")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_acl(raw_acl: Any) -> NormalizedAcl | None:
    """None means the ACL metadata is missing or structurally invalid — the
    caller must reject the document. An empty-but-present {"users": [],
    "groups": []} is a valid, deliberate NormalizedAcl([], []).
    """
    if not isinstance(raw_acl, dict):
        return None
    users = raw_acl.get("users")
    groups = raw_acl.get("groups")
    if not isinstance(users, list) or not isinstance(groups, list):
        return None
    if not all(isinstance(u, str) for u in users) or not all(isinstance(g, str) for g in groups):
        return None
    return NormalizedAcl(users=list(users), groups=list(groups))
