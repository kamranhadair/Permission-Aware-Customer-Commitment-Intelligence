"""Call transcript parser. Pure format transformation — no DB access."""

from __future__ import annotations

from typing import Any

from app.ingestion.errors import ParseError
from app.ingestion.parsers.common import parse_acl, require_datetime, require_str
from app.ingestion.types import NormalizedDocument

SOURCE = "call"


def parse(raw: dict[str, Any]) -> tuple[list[NormalizedDocument], list[ParseError]]:
    documents: list[NormalizedDocument] = []
    errors: list[ParseError] = []

    for call in raw.get("calls", []):
        external_id = call.get("id")
        try:
            documents.append(_parse_call(call))
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(ParseError(source=SOURCE, external_id=external_id, reason=str(exc)))

    return documents, errors


def _parse_call(call: dict[str, Any]) -> NormalizedDocument:
    return NormalizedDocument(
        external_id=require_str(call, "id"),
        source=SOURCE,
        account_slug=require_str(call, "account_slug"),
        title=require_str(call, "title"),
        content=require_str(call, "transcript"),
        occurred_at=require_datetime(call, "occurred_at"),
        sensitivity=require_str(call, "sensitivity"),
        acl=parse_acl(call.get("acl")),
    )
