"""Support ticket parser. Pure format transformation — no DB access, no
account/user/group resolution. That belongs to the ingestion service.
"""

from __future__ import annotations

from typing import Any

from app.ingestion.errors import ParseError
from app.ingestion.parsers.common import parse_acl, require_datetime, require_str
from app.ingestion.types import NormalizedDocument

SOURCE = "support"


def parse(raw: dict[str, Any]) -> tuple[list[NormalizedDocument], list[ParseError]]:
    documents: list[NormalizedDocument] = []
    errors: list[ParseError] = []

    for ticket in raw.get("tickets", []):
        external_id = ticket.get("id")
        try:
            documents.append(_parse_ticket(ticket))
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(ParseError(source=SOURCE, external_id=external_id, reason=str(exc)))

    return documents, errors


def _parse_ticket(ticket: dict[str, Any]) -> NormalizedDocument:
    return NormalizedDocument(
        external_id=require_str(ticket, "id"),
        source=SOURCE,
        account_slug=require_str(ticket, "account_slug"),
        title=require_str(ticket, "subject"),
        content=require_str(ticket, "description"),
        occurred_at=require_datetime(ticket, "created_at"),
        sensitivity=require_str(ticket, "sensitivity"),
        acl=parse_acl(ticket.get("acl")),
    )
