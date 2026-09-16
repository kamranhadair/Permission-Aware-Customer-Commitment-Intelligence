"""Wraps app.retrieval.evaluate as a pytest test. Skipped (not failed) when
sentence-transformers isn't installed, so the default `pytest` run stays
fast/hermetic — the paraphrase/semantic golden queries are only meaningful
against the real BAAI/bge-small-en-v1.5 provider."""

import importlib.util

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("sentence_transformers") is None,
    reason="requires the 'embeddings' extra (pip install -e '.[dev,embeddings]')",
)


def test_golden_query_set_has_zero_unauthorized_candidates():
    from app.retrieval.evaluate import main

    assert main() == 0
