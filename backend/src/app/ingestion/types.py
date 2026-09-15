"""The normalized shape every source parser produces, and the result shape
the ingestion service returns for each document. Parsers never construct
anything outside this module's types; the service never sees raw source
JSON.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class NormalizedAcl:
    """A source's declared ACL. Distinguishing this from `None` on
    `NormalizedDocument.acl` is what lets the service tell "the source
    declared zero principals" apart from "the source didn't tell us
    anything about permissions" — see ingestion/service.py.
    """

    users: list[str]  # emails, org-scoped
    groups: list[str]  # group names, org-scoped


@dataclass(frozen=True)
class NormalizedDocument:
    external_id: str
    source: str  # matches source_documents' CHECK enum: 'call' | 'support' | 'slack' | ...
    account_slug: str
    title: str
    content: str
    occurred_at: datetime
    sensitivity: str
    acl: NormalizedAcl | None  # None = ACL metadata missing/malformed -> reject


IngestOutcome = Literal["created", "updated", "unchanged", "rejected", "blocked"]


@dataclass(frozen=True)
class IngestResult:
    external_id: str
    source: str
    account_slug: str
    outcome: IngestOutcome
    reason: str | None = None
    document_id: int | None = None
