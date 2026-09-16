"""Proves the runner's session-ownership contract exactly as specified:

- a caller-supplied session is used as-is (never replaced by a fresh
  SessionLocal()) and never closed by the runner — the caller (a pytest
  fixture, or any other embedder) owns its own rollback/close.
- a runner-owned session (the standalone `db=None` path) always attempts
  cleanup of the exact org it seeded in `finally`, even when a case raises
  partway through scoring — and the original exception still propagates
  unmasked.

These tests exercise the real TEST_DATABASE_URL twice per test in the
owned-session case: the runner's own SessionLocal() connection (forced to
TEST_DATABASE_URL by conftest.py before any app import) does the seeding/
cleanup, and the pytest `db` fixture's separate connection verifies the
outcome — two connections to the same physical database, which is exactly
what proves cleanup's commits are real, not just visible within one
session's identity map.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from app.evaluation import runner
from app.models import Organization


def test_injected_session_is_used_as_is_and_never_closed(db, monkeypatch):
    session_local_calls = []
    monkeypatch.setattr(
        runner, "SessionLocal", lambda: session_local_calls.append(1) or pytest.fail("must not call SessionLocal()")
    )

    close_spy = MagicMock(wraps=db.close)
    with patch.object(db, "close", close_spy):
        report = runner.run(mode="security", case_id="dl-01", db=db)

    assert report.case_results[0].case_id == "dl-01"
    assert session_local_calls == []
    close_spy.assert_not_called()

    # The caller's session must still be usable afterward — proof the
    # runner never closed or otherwise tore it down.
    db.execute(select(Organization.id)).all()


def test_owned_session_cleans_up_and_reraises_when_a_case_raises(db, monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("simulated scoring failure")

    # dl-01 is a generation-capable (non retrieval_only) case, so security
    # mode dispatches it to _score_security_generation_case, not
    # _score_retrieval_case.
    monkeypatch.setattr(runner, "_score_security_generation_case", _boom)

    with pytest.raises(RuntimeError, match="simulated scoring failure"):
        runner.run(mode="security", case_id="dl-01")  # no db= -> owns_session=True, real SessionLocal()

    # Verify via the pytest fixture's OWN connection (not the runner's) that
    # no "Evaluation Org" was left behind despite the mid-run exception.
    remaining = db.scalars(select(Organization.id).where(Organization.name.like("Evaluation Org%"))).all()
    assert remaining == [], f"cleanup did not run (or failed) after a mid-run exception: {remaining}"


def test_owned_session_cleans_up_on_success_too(db):
    report = runner.run(mode="security", case_id="dl-01")
    assert report.case_results[0].case_id == "dl-01"

    remaining = db.scalars(select(Organization.id).where(Organization.name.like("Evaluation Org%"))).all()
    assert remaining == [], f"a successful owned-session run must also clean up after itself: {remaining}"
