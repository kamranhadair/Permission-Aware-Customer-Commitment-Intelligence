"""Thin CLI smoke test: argument parsing, org resolution, and exit-code
behavior. The service/parsers already have their own dedicated test
files — this only checks the orchestration layer wired on top of them.
"""

from app.ingestion import cli
from tests.factories import make_account, make_org, make_user


def test_cli_exits_nonzero_for_unknown_org(monkeypatch, tmp_path, db):
    monkeypatch.setattr(cli, "SessionLocal", lambda: db)
    fixture = tmp_path / "tickets.json"
    fixture.write_text('{"tickets": []}')

    exit_code = cli.main(["support", str(fixture), "--org-id", "999999"])

    assert exit_code == 1


def test_cli_exits_zero_when_everything_ingests_cleanly(monkeypatch, tmp_path, db):
    org = make_org(db, "Org")
    make_account(db, org, "acme-corp")
    make_user(db, org, "alice@x.example")
    monkeypatch.setattr(cli, "SessionLocal", lambda: db)

    fixture = tmp_path / "tickets.json"
    fixture.write_text(
        """
        {"tickets": [{
            "id": "T-1", "account_slug": "acme-corp", "subject": "S", "description": "D",
            "created_at": "2026-01-01T00:00:00Z", "sensitivity": "internal",
            "acl": {"users": ["alice@x.example"], "groups": []}
        }]}
        """
    )

    exit_code = cli.main(["support", str(fixture), "--org-id", str(org.id)])

    assert exit_code == 0


def test_cli_exits_nonzero_when_a_record_is_rejected(monkeypatch, tmp_path, db):
    org = make_org(db, "Org")
    make_account(db, org, "acme-corp")
    monkeypatch.setattr(cli, "SessionLocal", lambda: db)

    fixture = tmp_path / "tickets.json"
    fixture.write_text(
        """
        {"tickets": [{
            "id": "T-1", "account_slug": "no-such-account", "subject": "S", "description": "D",
            "created_at": "2026-01-01T00:00:00Z", "sensitivity": "internal",
            "acl": {"users": [], "groups": []}
        }]}
        """
    )

    exit_code = cli.main(["support", str(fixture), "--org-id", str(org.id)])

    assert exit_code == 1
