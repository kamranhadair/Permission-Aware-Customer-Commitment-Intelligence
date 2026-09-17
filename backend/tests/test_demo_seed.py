"""app.demo.seed: persistent, convergent, and independent of
app.evaluation.*. Proves the demo fixture data actually demonstrates a
real permission split through the unmodified Milestone 2 resolver, not
just that rows got inserted.
"""

from sqlalchemy import func, select

from app.demo.org import DEMO_ORG_NAME, AmbiguousDemoOrgError, resolve_demo_org
from app.demo.seed import seed
from app.models import Account, Chunk, Commitment, Group, Organization, SourceDocument, User
from app.permissions.resolver import get_user_context, get_visible_commitments
from app.retrieval.embeddings import FakeEmbeddingProvider
from tests.factories import make_account, make_chunk, make_document, make_org


def test_fresh_seed_converges_and_demonstrates_permission_split(db):
    report = seed(db, embedding_provider=FakeEmbeddingProvider())
    assert not report.failed, report.render()

    org = resolve_demo_org(db)
    assert org is not None
    acme = db.scalar(select(Account).where(Account.org_id == org.id, Account.slug == "acme-corp"))
    maya = db.scalar(select(User).where(User.org_id == org.id, User.email == "maya@demo.example"))
    lena = db.scalar(select(User).where(User.org_id == org.id, User.email == "lena@demo.example"))
    assert acme is not None and maya is not None and lena is not None

    maya_ctx = get_user_context(db, maya.id)
    lena_ctx = get_user_context(db, lena.id)
    maya_commitments = {c.statement: c for c in get_visible_commitments(db, maya_ctx, acme.id)}
    lena_commitments = {c.statement: c for c in get_visible_commitments(db, lena_ctx, acme.id)}

    # Both personas see both commitments (each has permitted supporting evidence).
    assert "Enterprise SSO by November 15" in maya_commitments
    assert "Enterprise SSO by November 15" in lena_commitments
    assert "Complete security questionnaire" in maya_commitments
    assert "Complete security questionnaire" in lena_commitments

    # Only Product (Lena) can see the conflicting internal Slack evidence —
    # the whole point of the demo fixture.
    assert maya_commitments["Enterprise SSO by November 15"].conflicting == []
    assert len(lena_commitments["Enterprise SSO by November 15"].conflicting) == 1


def test_rerun_converges_without_duplicating(db):
    first = seed(db, embedding_provider=FakeEmbeddingProvider())
    assert not first.failed, first.render()

    def _counts():
        org = resolve_demo_org(db)
        return {
            "orgs": db.scalar(select(func.count()).select_from(Organization).where(Organization.name == DEMO_ORG_NAME)),
            "accounts": db.scalar(select(func.count()).select_from(Account).where(Account.org_id == org.id)),
            "users": db.scalar(select(func.count()).select_from(User).where(User.org_id == org.id)),
            "groups": db.scalar(select(func.count()).select_from(Group).where(Group.org_id == org.id)),
            "commitments": db.scalar(
                select(func.count()).select_from(Commitment).join(Account).where(Account.org_id == org.id)
            ),
        }

    before = _counts()
    second = seed(db, embedding_provider=FakeEmbeddingProvider())
    assert not second.failed, second.render()
    after = _counts()

    assert before == after
    assert before["orgs"] == 1


def test_ambiguous_demo_org_aborts_before_any_write(db):
    org_a = Organization(name=DEMO_ORG_NAME)
    org_b = Organization(name=DEMO_ORG_NAME)
    db.add_all([org_a, org_b])
    db.flush()

    try:
        seed(db, embedding_provider=FakeEmbeddingProvider())
        assert False, "expected AmbiguousDemoOrgError"
    except AmbiguousDemoOrgError as exc:
        assert set(exc.org_ids) == {org_a.id, org_b.id}

    # Nothing beyond the two pre-existing org rows was created.
    assert db.scalar(select(func.count()).select_from(Account)) == 0
    assert db.scalar(select(func.count()).select_from(User)) == 0


def test_embedding_step_never_touches_another_orgs_unembedded_chunks(db):
    other_org = make_org(db, "Unrelated Dev Org")
    other_account = make_account(db, other_org, "unrelated-acct")
    other_chunk = make_chunk(db, make_document(db, other_account), content="unrelated dev data")

    report = seed(db, embedding_provider=FakeEmbeddingProvider())
    assert not report.failed, report.render()

    db.refresh(other_chunk)
    assert other_chunk.embedding is None

    # And the seed's own chunks (a different org) did get embedded.
    org = resolve_demo_org(db)
    demo_chunks = list(
        db.scalars(
            select(Chunk)
            .join(SourceDocument, SourceDocument.id == Chunk.document_id)
            .join(Account, Account.id == SourceDocument.account_id)
            .where(Account.org_id == org.id)
        )
    )
    assert demo_chunks, "expected the demo seed to have ingested at least one chunk"
    for chunk in demo_chunks:
        assert chunk.embedding is not None
