"""Proves golden-only, evaluator-privileged fields (`note`, `forbidden_evidence`,
`expected_conflict`, ...) never reach the generator — they exist purely for
scoring, and Milestone 6 design section 6 requires the product-facing
generation path to see nothing beyond query/account_slug/persona, exactly
like a real end user. A future refactor that accidentally threaded a golden
field into the prompt would fail this test immediately.
"""

from __future__ import annotations

from app.evaluation.personas import EvalSeed
from app.evaluation.runner import _score_generation_case
from app.evaluation.schema import GoldenCase, StableEvidenceRef
from app.generation.provider import FakeAnswerGenerator
from app.generation.types import GeneratedAnswer
from app.permissions.resolver import get_user_context
from app.retrieval.embeddings import FakeEmbeddingProvider
from tests.factories import grant_group_acl, make_account, make_chunk, make_document, make_group, make_org, make_user

SENTINEL = "SENTINEL-PRIVILEGED-TEXT-DO-NOT-LEAK-93f1"


def test_privileged_golden_fields_never_reach_generator_query_or_context(db):
    org = make_org(db, "Org")
    org2 = make_org(db, "Org2")
    account = make_account(db, org, "acct")
    group = make_group(db, org, "grp")
    user = make_user(db, org, "u@example.com")
    from tests.factories import add_membership

    add_membership(db, user, group)
    doc = make_document(db, account, source="call", title="Doc title", sensitivity="internal")
    grant_group_acl(db, doc, group)
    content = "Ordinary permitted evidence content answering what the evidence says."
    chunk = make_chunk(db, doc, content=content)
    provider = FakeEmbeddingProvider()
    chunk.embedding = provider.embed_documents([content])[0]
    db.flush()

    seed = EvalSeed(org=org, cross_org=org2, accounts={"acct": account}, users={"u": user}, groups={"grp": group})

    case = GoldenCase(
        id="priv-01",
        category="permission_refusal",
        persona="u",
        account_slug="acct",
        query="What does the evidence say?",
        expected_status="insufficient_evidence",
        forbidden_evidence=[StableEvidenceRef(source="call", external_id=SENTINEL)],
        note=f"privileged evaluator note containing {SENTINEL}",
    )

    generator = FakeAnswerGenerator(respond_with=GeneratedAnswer(status="insufficient_evidence", claims=[]))
    user_ctx = get_user_context(db, user.id)

    _score_generation_case(db, seed, user_ctx, FakeEmbeddingProvider(), generator, case, mode="generation")

    assert generator.last_query == case.query, "the generator must receive exactly the case's query, nothing appended"
    assert SENTINEL not in (generator.last_query or "")

    if generator.last_context is not None:
        for chunk in generator.last_context.evidence:
            assert SENTINEL not in chunk.content
            assert SENTINEL not in chunk.title
        for commitment in generator.last_context.commitments:
            assert SENTINEL not in commitment.statement
