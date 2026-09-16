"""Wraps the canonical Milestone 6 evaluation runner's `retrieval` mode as a
pytest test. Skipped (not failed) when sentence-transformers isn't
installed, so the default `pytest` run stays fast/hermetic — the paraphrase/
semantic golden cases are only meaningful against the real
BAAI/bge-small-en-v1.5 provider. Superseded the standalone
`retrieval/evaluate.py` script (Milestone 4), retired in Milestone 6 in
favor of `python -m app.evaluation.run --mode retrieval` as the single
canonical evaluation entry point.
"""

import importlib.util

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("sentence_transformers") is None,
    reason="requires the 'embeddings' extra (pip install -e '.[dev,embeddings]')",
)


def test_golden_dataset_has_zero_unauthorized_candidates_under_real_embeddings(db):
    from app.evaluation import runner

    report = runner.run(mode="retrieval", db=db)
    assert report.security_all_clear, [
        (r.case_id, r.security) for r in report.case_results if r.security_violation_count > 0
    ]
