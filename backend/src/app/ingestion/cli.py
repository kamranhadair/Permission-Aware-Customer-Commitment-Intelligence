"""Development ingestion CLI. Orchestration and reporting only — no
persistence or transaction logic lives here (that's `service.py`).

    python -m app.ingestion.cli support fixtures/support/tickets.json --org-id 1
    python -m app.ingestion.cli calls   fixtures/calls/calls.json     --org-id 1
    python -m app.ingestion.cli slack   fixtures/slack               --org-id 1

`--org-id` is required: a real connector is deployed for one org, so org
is run-level configuration, never something a source record can assert
about itself. If it doesn't resolve, the whole run fails before touching
any records. Ingestion does not provision organizations, accounts,
users, groups, or memberships — those must already exist.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from app.db import SessionLocal
from app.ingestion.errors import ParseError
from app.ingestion.parsers import calls as calls_parser
from app.ingestion.parsers import slack as slack_parser
from app.ingestion.parsers import support as support_parser
from app.ingestion.service import ingest_batch
from app.ingestion.types import IngestResult, NormalizedDocument
from app.models import Organization

_OUTCOMES = ("created", "updated", "unchanged", "blocked", "rejected")


def _load_json(path: Path) -> dict[str, Any]:
    with path.open() as f:
        return json.load(f)


def _parse_source(source: str, path: Path) -> tuple[list[NormalizedDocument], list[ParseError]]:
    if source == "support":
        return support_parser.parse(_load_json(path))
    if source == "calls":
        return calls_parser.parse(_load_json(path))
    if source == "slack":
        channels = _load_json(path / "channels.json")
        messages = _load_json(path / "messages.json")
        return slack_parser.parse(channels, messages)
    raise ValueError(f"unknown source '{source}'")  # unreachable: argparse `choices` guards this


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.ingestion.cli")
    parser.add_argument("source", choices=["support", "calls", "slack"])
    parser.add_argument("path", help="file for support/calls; directory (channels.json + messages.json) for slack")
    parser.add_argument("--org-id", type=int, required=True)
    args = parser.parse_args(argv)

    session = SessionLocal()
    try:
        org = session.get(Organization, args.org_id)
        if org is None:
            print(f"error: organization {args.org_id} does not exist")
            return 1

        documents, parse_errors = _parse_source(args.source, Path(args.path))
        results = ingest_batch(session, args.org_id, documents)
    finally:
        session.close()

    _print_summary(results, parse_errors)
    has_failures = bool(parse_errors) or any(r.outcome in ("rejected", "blocked") for r in results)
    return 1 if has_failures else 0


def _print_summary(results: list[IngestResult], parse_errors: list[ParseError]) -> None:
    counts = {outcome: 0 for outcome in _OUTCOMES}
    for result in results:
        counts[result.outcome] += 1

    print(
        ", ".join(f"{counts[outcome]} {outcome}" for outcome in _OUTCOMES)
        + f", {len(parse_errors)} parse error(s)"
    )
    for result in results:
        if result.outcome in ("rejected", "blocked"):
            print(f"  [{result.outcome}] {result.source}:{result.external_id} ({result.account_slug}): {result.reason}")
    for error in parse_errors:
        print(f"  [parse error] {error.source}:{error.external_id}: {error.reason}")


if __name__ == "__main__":
    sys.exit(main())
