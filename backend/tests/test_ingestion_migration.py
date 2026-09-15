"""Proves migration 0002 is safe against a database that already has
Milestone 2 rows in it — the exact scenario the migration was designed
for (see CLAUDE.md's Milestone 3 status block and the migration's own
docstring). This test manages its own schema/engine outside the shared
`db`/`engine` fixtures because it deliberately steps through an
intermediate migration state those fixtures assume is already at head.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from tests.conftest import TEST_DATABASE_URL

BACKEND_DIR = Path(__file__).resolve().parent.parent
LEGACY_REVISION = "3715d9011473"  # the real revision id of 0001_create_core_schema.py


def _alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


def test_0002_migration_backfills_legacy_rows_and_preserves_readability():
    cfg = _alembic_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, LEGACY_REVISION)

    engine = create_engine(TEST_DATABASE_URL, future=True)
    try:
        with engine.begin() as conn:
            org_id = conn.execute(
                text("INSERT INTO organizations (name) VALUES ('Legacy Org') RETURNING id")
            ).scalar_one()
            account_id = conn.execute(
                text("INSERT INTO accounts (org_id, slug, name) VALUES (:org_id, 'legacy-acct', 'Legacy') RETURNING id"),
                {"org_id": org_id},
            ).scalar_one()
            user_id = conn.execute(
                text("INSERT INTO users (org_id, email, display_name) VALUES (:org_id, 'legacy@x.example', 'Legacy') RETURNING id"),
                {"org_id": org_id},
            ).scalar_one()
            doc_id = conn.execute(
                text(
                    "INSERT INTO source_documents (account_id, source, title, sensitivity, occurred_at) "
                    "VALUES (:account_id, 'support', 'Legacy Doc', 'internal', '2026-01-01T00:00:00Z') RETURNING id"
                ),
                {"account_id": account_id},
            ).scalar_one()
            conn.execute(
                text("INSERT INTO document_user_acl (document_id, user_id) VALUES (:doc_id, :user_id)"),
                {"doc_id": doc_id, "user_id": user_id},
            )
            chunk_ids = [
                conn.execute(
                    text("INSERT INTO chunks (document_id, content) VALUES (:doc_id, :content) RETURNING id"),
                    {"doc_id": doc_id, "content": content},
                ).scalar_one()
                for content in ("first chunk", "second chunk", "third chunk")
            ]

        command.upgrade(cfg, "head")

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT external_id, content_hash FROM source_documents WHERE id = :id"), {"id": doc_id}
            ).one()
            assert row.external_id is None
            assert row.content_hash is None

            sequences = conn.execute(
                text("SELECT id, sequence FROM chunks WHERE document_id = :id ORDER BY id"), {"id": doc_id}
            ).all()
            assert [s.id for s in sequences] == chunk_ids
            assert [s.sequence for s in sequences] == [0, 1, 2]
    finally:
        engine.dispose()
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")
