"""These are the most important behavioral tests in the suite: they prove
commitment visibility is derived from evidence access, not just that
evidence lists get filtered after the fact."""

from tests.factories import (
    grant_user_acl,
    link_evidence,
    make_account,
    make_chunk,
    make_commitment,
    make_document,
    make_org,
    make_user,
)

EXPECTED_COMMITMENT_KEYS = {
    "id",
    "statement",
    "promised_by",
    "promise_date",
    "delivery_date",
    "authority",
    "status",
    "supporting_evidence",
    "conflicting_evidence",
}


def test_commitment_with_permitted_supporting_evidence_is_visible(db, client):
    org = make_org(db)
    account = make_account(db, org, "acme")
    doc = make_document(db, account, source="call", title="Customer call")
    chunk = make_chunk(db, doc, content="We'll ship SSO in November")
    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, doc, user)

    commitment = make_commitment(db, account, statement="SSO by Nov 15")
    link_evidence(db, commitment, chunk, "supporting")

    resp = client.get("/accounts/acme/commitments", headers={"X-User-Id": str(user.id)})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["statement"] == "SSO by Nov 15"
    assert [c["content"] for c in body[0]["supporting_evidence"]] == ["We'll ship SSO in November"]
    assert body[0]["conflicting_evidence"] == []


def test_commitment_with_no_permitted_supporting_evidence_is_omitted(db, client):
    org = make_org(db)
    account = make_account(db, org, "acme")
    doc = make_document(db, account)
    chunk = make_chunk(db, doc)
    owner = make_user(db, org, "owner@x.com")
    grant_user_acl(db, doc, owner)  # only the owner can see this evidence

    commitment = make_commitment(db, account)
    link_evidence(db, commitment, chunk, "supporting")

    outsider = make_user(db, org, "outsider@x.com")
    other_doc = make_document(db, account)
    grant_user_acl(db, other_doc, outsider)  # account itself is visible; the commitment's evidence is not

    resp = client.get("/accounts/acme/commitments", headers={"X-User-Id": str(outsider.id)})
    assert resp.status_code == 200
    assert resp.json() == []


def test_permitted_support_and_forbidden_conflict_hides_conflict_existence(db, client):
    org = make_org(db)
    account = make_account(db, org, "acme")
    supporting_doc = make_document(db, account, title="Customer call")
    conflicting_doc = make_document(db, account, title="Private product Slack", sensitivity="confidential")
    supporting_chunk = make_chunk(db, supporting_doc, content="customer-call evidence")
    conflicting_chunk = make_chunk(db, conflicting_doc, content="private-product-slack evidence")

    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, supporting_doc, user)  # can see supporting, NOT conflicting

    commitment = make_commitment(db, account, statement="SSO by Nov 15")
    link_evidence(db, commitment, supporting_chunk, "supporting")
    link_evidence(db, commitment, conflicting_chunk, "conflicting")

    resp = client.get("/accounts/acme/commitments", headers={"X-User-Id": str(user.id)})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["conflicting_evidence"] == []
    # No has_hidden_conflict / count / any field hinting at withheld evidence.
    assert set(body[0].keys()) == EXPECTED_COMMITMENT_KEYS


def test_forbidden_support_and_permitted_conflict_omits_commitment_entirely(db, client):
    org = make_org(db)
    account = make_account(db, org, "acme")
    supporting_doc = make_document(db, account)
    conflicting_doc = make_document(db, account)
    supporting_chunk = make_chunk(db, supporting_doc)
    conflicting_chunk = make_chunk(db, conflicting_doc)

    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, conflicting_doc, user)  # can see the conflict, NOT the support

    commitment = make_commitment(db, account)
    link_evidence(db, commitment, supporting_chunk, "supporting")
    link_evidence(db, commitment, conflicting_chunk, "conflicting")

    resp = client.get("/accounts/acme/commitments", headers={"X-User-Id": str(user.id)})
    assert resp.status_code == 200
    assert resp.json() == []


def test_all_evidence_forbidden_omits_commitment_entirely(db, client):
    org = make_org(db)
    account = make_account(db, org, "acme")
    supporting_doc = make_document(db, account)
    conflicting_doc = make_document(db, account)
    supporting_chunk = make_chunk(db, supporting_doc)
    conflicting_chunk = make_chunk(db, conflicting_doc)

    owner = make_user(db, org, "owner@x.com")
    grant_user_acl(db, supporting_doc, owner)
    grant_user_acl(db, conflicting_doc, owner)

    commitment = make_commitment(db, account)
    link_evidence(db, commitment, supporting_chunk, "supporting")
    link_evidence(db, commitment, conflicting_chunk, "conflicting")

    outsider = make_user(db, org, "outsider@x.com")
    other_doc = make_document(db, account)
    grant_user_acl(db, other_doc, outsider)  # account visible, but zero evidence access

    resp = client.get("/accounts/acme/commitments", headers={"X-User-Id": str(outsider.id)})
    assert resp.status_code == 200
    assert resp.json() == []


def test_commitments_endpoint_404s_when_account_not_visible(db, client):
    org = make_org(db)
    user = make_user(db, org, "u1@x.com")

    resp = client.get("/accounts/does-not-exist/commitments", headers={"X-User-Id": str(user.id)})
    assert resp.status_code == 404


def test_malformed_cross_account_evidence_link_does_not_expose_commitment(db, client):
    """A commitment belongs to Acme; a malformed commitment_evidence row
    links its supporting evidence to a chunk that actually belongs to a
    different account (Beta). Even though the user CAN see that Beta
    chunk directly, it must not make the Acme commitment visible."""
    org = make_org(db)
    acme = make_account(db, org, "acme")
    beta = make_account(db, org, "beta")

    beta_doc = make_document(db, beta)
    beta_chunk = make_chunk(db, beta_doc)

    acme_doc = make_document(db, acme)  # gives the user visibility into the Acme account itself

    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, beta_doc, user)  # user CAN see the Beta chunk directly
    grant_user_acl(db, acme_doc, user)

    commitment = make_commitment(db, acme, statement="Acme commitment")
    link_evidence(db, commitment, beta_chunk, "supporting")  # malformed cross-account link

    resp = client.get("/accounts/acme/commitments", headers={"X-User-Id": str(user.id)})
    assert resp.status_code == 200
    assert resp.json() == []
