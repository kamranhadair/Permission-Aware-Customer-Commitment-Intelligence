"""Slack export parser. Joins channels.json (channel metadata: account,
sensitivity, ACL) with messages.json (individual messages) into one
NormalizedDocument per conversation thread, or per standalone message.

Channel membership is the sole source of account/sensitivity/ACL for
every document produced here — there is no message- or thread-level ACL.
A channel is an unbounded stream, so one document per whole channel would
make chunk replacement (and evidence provenance) unstable on every new
message; threads/standalone messages are naturally bounded units instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.ingestion.errors import ParseError
from app.ingestion.parsers.common import parse_acl, require_str
from app.ingestion.types import NormalizedAcl, NormalizedDocument

SOURCE = "slack"


@dataclass(frozen=True)
class _Channel:
    id: str
    name: str
    account_slug: str
    sensitivity: str
    acl: NormalizedAcl | None


def parse(
    channels_raw: dict[str, Any], messages_raw: dict[str, Any]
) -> tuple[list[NormalizedDocument], list[ParseError]]:
    errors: list[ParseError] = []
    channels = _parse_channels(channels_raw, errors)

    messages_by_channel: dict[str, list[dict[str, Any]]] = {}
    for message in messages_raw.get("messages", []):
        channel_id = message.get("channel_id")
        if not isinstance(channel_id, str) or channel_id not in channels:
            errors.append(
                ParseError(
                    source=SOURCE,
                    external_id=_best_effort_id(message),
                    reason=f"message references unknown channel_id {channel_id!r}",
                )
            )
            continue
        messages_by_channel.setdefault(channel_id, []).append(message)

    documents: list[NormalizedDocument] = []
    for channel_id, channel in channels.items():
        docs, channel_errors = _group_channel_messages(channel, messages_by_channel.get(channel_id, []))
        documents.extend(docs)
        errors.extend(channel_errors)

    return documents, errors


def _parse_channels(raw: dict[str, Any], errors: list[ParseError]) -> dict[str, _Channel]:
    channels: dict[str, _Channel] = {}
    for raw_channel in raw.get("channels", []):
        channel_id = raw_channel.get("id")
        try:
            channels[require_str(raw_channel, "id")] = _Channel(
                id=require_str(raw_channel, "id"),
                name=require_str(raw_channel, "name"),
                account_slug=require_str(raw_channel, "account_slug"),
                sensitivity=require_str(raw_channel, "sensitivity"),
                acl=parse_acl(raw_channel.get("acl")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(ParseError(source=SOURCE, external_id=channel_id, reason=str(exc)))
    return channels


def _best_effort_id(message: dict[str, Any]) -> str | None:
    channel_id = message.get("channel_id")
    ts = message.get("ts")
    if isinstance(channel_id, str) and isinstance(ts, str):
        return f"{channel_id}:{ts}"
    return None


def _group_channel_messages(
    channel: _Channel, messages: list[dict[str, Any]]
) -> tuple[list[NormalizedDocument], list[ParseError]]:
    documents: list[NormalizedDocument] = []
    errors: list[ParseError] = []

    by_ts: dict[str, dict[str, Any]] = {}
    replies_by_thread_ts: dict[str, list[dict[str, Any]]] = {}
    for message in messages:
        ts = message.get("ts")
        if not isinstance(ts, str):
            errors.append(ParseError(source=SOURCE, external_id=None, reason="message missing required field 'ts'"))
            continue
        by_ts[ts] = message
        thread_ts = message.get("thread_ts")
        if isinstance(thread_ts, str):
            replies_by_thread_ts.setdefault(thread_ts, []).append(message)

    consumed_ts: set[str] = set()

    for thread_ts, replies in replies_by_thread_ts.items():
        root = by_ts.get(thread_ts)
        if root is None:
            for reply in replies:
                errors.append(
                    ParseError(
                        source=SOURCE,
                        external_id=_best_effort_id(reply),
                        reason=f"reply's thread_ts {thread_ts!r} does not match any message in channel {channel.id!r}",
                    )
                )
            continue

        try:
            thread_messages = {thread_ts: root, **{r["ts"]: r for r in replies}}
            documents.append(_build_document(channel, thread_ts, list(thread_messages.values()), is_thread=True))
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(ParseError(source=SOURCE, external_id=f"{channel.id}:{thread_ts}", reason=str(exc)))

        consumed_ts.add(thread_ts)
        consumed_ts.update(r["ts"] for r in replies)

    for ts, message in by_ts.items():
        if ts in consumed_ts or isinstance(message.get("thread_ts"), str):
            continue
        try:
            documents.append(_build_document(channel, ts, [message], is_thread=False))
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(ParseError(source=SOURCE, external_id=f"{channel.id}:{ts}", reason=str(exc)))

    return documents, errors


def _build_document(
    channel: _Channel, key_ts: str, messages: list[dict[str, Any]], *, is_thread: bool
) -> NormalizedDocument:
    ordered = sorted(messages, key=lambda m: float(m["ts"]))
    lines = [f"{_ts_to_iso(m['ts'])} {require_str(m, 'user')}: {require_str(m, 'text')}" for m in ordered]
    latest_ts = max(float(m["ts"]) for m in ordered)

    kind = "thread" if is_thread else "message"
    return NormalizedDocument(
        external_id=f"{channel.id}:{key_ts}",
        source=SOURCE,
        account_slug=channel.account_slug,
        title=f"Slack {kind} in #{channel.name}",
        content="\n\n".join(lines),
        occurred_at=datetime.fromtimestamp(latest_ts, tz=timezone.utc),
        sensitivity=channel.sensitivity,
        acl=channel.acl,
    )


def _ts_to_iso(ts: str) -> str:
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
