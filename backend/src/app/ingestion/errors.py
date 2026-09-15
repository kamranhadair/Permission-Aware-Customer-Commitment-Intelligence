"""Parser-level error type. A ParseError never aborts a whole file — the
parser collects them alongside whatever NormalizedDocuments it could
produce, and the caller (service/CLI) reports them without stopping.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParseError:
    source: str
    external_id: str | None  # best-effort identifier for the bad record, if any was recoverable
    reason: str
