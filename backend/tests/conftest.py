import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent

# Load backend/.env into the real process environment (override=False: a
# real shell env var still wins) so TEST_DATABASE_URL from that file is
# actually honored, not just coincidentally matched by a hardcoded default.
load_dotenv(BACKEND_DIR / ".env", override=False)

# Force the app (and Alembic's env.py, which reads app.config.settings) to
# talk to the TEST database for the entire session, never the dev database.
# This must happen before anything imports app.config.
if "TEST_DATABASE_URL" not in os.environ:
    raise RuntimeError(
        "TEST_DATABASE_URL is not set. Define it in backend/.env or export it "
        "in the shell before running the test suite."
    )
TEST_DATABASE_URL = os.environ["TEST_DATABASE_URL"]
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.db import get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _migrated_schema():
    """Run the real Alembic migrations against the real test Postgres database."""
    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.downgrade(alembic_cfg, "base")
    command.upgrade(alembic_cfg, "head")
    yield


@pytest.fixture()
def engine():
    return create_engine(TEST_DATABASE_URL, future=True)


@pytest.fixture()
def db(engine):
    """One test = one outer transaction, rolled back at teardown for
    isolation — even though ingestion service code calls session.commit()
    per document (real per-document transactions being the whole point
    of that design). The standard SQLAlchemy recipe for this: the test's
    real work happens in a SAVEPOINT, and an event listener restarts a
    fresh SAVEPOINT every time the session's `commit()` ends one, so a
    "commit" from the code under test never reaches the outer transaction
    that this fixture rolls back at teardown.
    """
    from sqlalchemy import event

    connection = engine.connect()
    outer_transaction = connection.begin()
    session = sessionmaker(bind=connection, future=True)()
    session.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess, transaction):
        if transaction.nested and not transaction._parent.nested:
            sess.begin_nested()

    try:
        yield session
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db):
    """A TestClient whose get_db dependency is overridden to use the SAME
    session/transaction as the test, so seeded-but-uncommitted data is
    visible to the request without needing a real commit."""

    def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
