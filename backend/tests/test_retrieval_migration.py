"""Proves migrations 0003/0004 are safe against a database that already has
Milestone 3 rows in it (a populated, non-empty database), not just an
empty one — the same pattern as test_ingestion_migration.py."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from tests.conftest import TEST_DATABASE_URL

BACKEND_DIR = Path(__file__).resolve().parent.parent
PRE_RETRIEVAL_REVISION = "0002_ingestion_identity"


def _alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


def test_0003_and_0004_are_safe_against_a_populated_milestone_3_database():
    cfg = _alembic_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, PRE_RETRIEVAL_REVISION)

    engine = create_engine(TEST_DATABASE_URL, future=True)
    try:
        with engine.begin() as conn:
            org_id = conn.execute(
                text("INSERT INTO organizations (name) VALUES ('Pre-Retrieval Org') RETURNING id")
            ).scalar_one()
            account_id = conn.execute(
                text(
                    "INSERT INTO accounts (org_id, slug, name) VALUES (:org_id, 'pre-retrieval', 'Pre') RETURNING id"
                ),
                {"org_id": org_id},
            ).scalar_one()
            doc_id = conn.execute(
                text(
                    "INSERT INTO source_documents "
                    "(account_id, source, title, sensitivity, occurred_at, external_id, content_hash) "
                    "VALUES (:account_id, 'support', 'Pre-Retrieval Doc', 'internal', "
                    "'2026-01-01T00:00:00Z', 'PRE-1', 'deadbeef') RETURNING id"
                ),
                {"account_id": account_id},
            ).scalar_one()
            chunk_id = conn.execute(
                text(
                    "INSERT INTO chunks (document_id, content, sequence) "
                    "VALUES (:doc_id, 'pre-existing chunk content', 0) RETURNING id"
                ),
                {"doc_id": doc_id},
            ).scalar_one()

        command.upgrade(cfg, "head")

        with engine.connect() as conn:
            extension = conn.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            ).scalar()
            assert extension == 1

            row = conn.execute(
                text("SELECT embedding FROM chunks WHERE id = :id"), {"id": chunk_id}
            ).one()
            assert row.embedding is None  # pre-existing chunk starts unembedded, not a migration failure

            fts_hit = conn.execute(
                text(
                    "SELECT 1 FROM chunks WHERE id = :id "
                    "AND to_tsvector('english', content) @@ plainto_tsquery('english', 'pre-existing chunk')"
                ),
                {"id": chunk_id},
            ).scalar()
            assert fts_hit == 1  # the expression index needed no backfill to become searchable
    finally:
        engine.dispose()
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")


def test_downgrade_from_head_is_clean():
    cfg = _alembic_config()
    command.upgrade(cfg, "head")
    command.downgrade(cfg, PRE_RETRIEVAL_REVISION)

    engine = create_engine(TEST_DATABASE_URL, future=True)
    try:
        with engine.connect() as conn:
            columns = conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'chunks' AND column_name = 'embedding'"
                )
            ).all()
            assert columns == []
            indexes = conn.execute(
                text("SELECT indexname FROM pg_indexes WHERE indexname = 'idx_chunks_content_fts'")
            ).all()
            assert indexes == []
    finally:
        engine.dispose()
        command.upgrade(cfg, "head")
