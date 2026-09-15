"""Deterministic, project-owned chunking. No embeddings, no tokenizer
dependency, no overlap — overlap exists to protect semantic-retrieval
quality at chunk boundaries, and there is no retrieval yet to protect.

Splitting on paragraph boundaries first (falling back to a hard split for
any single paragraph that alone exceeds the budget) keeps chunks
deterministic for a given piece of content, which idempotent re-ingestion
relies on: the same content always produces the same chunk sequence.
"""

from __future__ import annotations

MAX_CHUNK_CHARS = 1000


def chunk_content(content: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    paragraphs = [p.strip() for p in content.split("\n\n")]
    paragraphs = [p for p in paragraphs if p]
    if not paragraphs:
        return []

    chunks: list[str] = []
    current = ""

    def flush() -> None:
        nonlocal current
        if current:
            chunks.append(current)
            current = ""

    for paragraph in paragraphs:
        pieces = _hard_split(paragraph, max_chars) if len(paragraph) > max_chars else [paragraph]
        for piece in pieces:
            if not current:
                current = piece
            elif len(current) + 2 + len(piece) <= max_chars:
                current = f"{current}\n\n{piece}"
            else:
                flush()
                current = piece
    flush()
    return chunks


def _hard_split(text: str, max_chars: int) -> list[str]:
    return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]
