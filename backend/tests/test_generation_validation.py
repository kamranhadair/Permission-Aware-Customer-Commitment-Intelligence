import pytest

from app.generation.errors import GenerationFailure
from app.generation.types import Claim, CommitmentContext, ContextChunk, GenerationContext
from app.generation.validation import parse_provider_payload, render_answer, validate_and_filter_claims
from datetime import datetime, timezone

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _evidence(citation_id: str) -> ContextChunk:
    return ContextChunk(
        citation_id=citation_id, chunk_id=int(citation_id[1:]), document_id=1, source="call", title="t",
        occurred_at=T0, content="c",
    )


def _context(evidence_ids: list[str], commitments: list[CommitmentContext] | None = None) -> GenerationContext:
    return GenerationContext(evidence=[_evidence(e) for e in evidence_ids], commitments=commitments or [])


# --- parse_provider_payload -------------------------------------------------


def test_parse_provider_payload_valid():
    payload = {
        "status": "answered",
        "claims": [{"text": "x", "citation_ids": ["E1"], "claim_type": "evidence"}],
    }
    result = parse_provider_payload(payload)
    assert result.status == "answered"
    assert result.claims[0].text == "x"


def test_parse_provider_payload_missing_required_field_raises_generation_failure():
    with pytest.raises(GenerationFailure):
        parse_provider_payload({"claims": []})  # missing "status"


def test_parse_provider_payload_wrong_type_raises_generation_failure():
    with pytest.raises(GenerationFailure):
        parse_provider_payload({"status": "answered", "claims": "not-a-list"})


# --- validate_and_filter_claims: evidence claims ----------------------------


def test_evidence_claim_with_valid_citation_kept():
    context = _context(["E1", "E2"])
    claim = Claim(text="fact", citation_ids=["E1"], claim_type="evidence")
    valid, summary = validate_and_filter_claims([claim], context)
    assert valid == [claim]
    assert summary.claims_dropped == 0


def test_evidence_claim_with_invented_citation_dropped():
    context = _context(["E1"])
    claim = Claim(text="fact", citation_ids=["E17"], claim_type="evidence")
    valid, summary = validate_and_filter_claims([claim], context)
    assert valid == []
    assert summary.claims_dropped == 1
    assert "E17" in summary.invalid_ids_seen


def test_evidence_claim_with_empty_citations_dropped():
    context = _context(["E1"])
    claim = Claim(text="fact", citation_ids=[], claim_type="evidence")
    valid, summary = validate_and_filter_claims([claim], context)
    assert valid == []
    assert summary.claims_dropped == 1


def test_evidence_claim_citing_a_commitment_id_dropped():
    """C* is never a member of the valid evidence-id set, so a claim citing
    it is rejected via the exact same path as an invented E-id."""
    context = _context(
        ["E1"],
        [CommitmentContext("C1", 1, "s", "product_approved", "on_track", ["E1"], [])],
    )
    claim = Claim(text="fact", citation_ids=["C1"], claim_type="evidence")
    valid, summary = validate_and_filter_claims([claim], context)
    assert valid == []
    assert "C1" in summary.invalid_ids_seen


def test_evidence_claim_with_commitment_context_id_set_is_malformed_and_dropped():
    context = _context(["E1"])
    claim = Claim(text="fact", citation_ids=["E1"], claim_type="evidence", commitment_context_id="C1")
    valid, _ = validate_and_filter_claims([claim], context)
    assert valid == []


# --- validate_and_filter_claims: commitment claims --------------------------


def _commitment_context(supporting: list[str], conflicting: list[str]) -> CommitmentContext:
    return CommitmentContext(
        citation_id="C1", commitment_id=1, statement="s", authority="product_approved", status="on_track",
        supporting_citation_ids=supporting, conflicting_citation_ids=conflicting,
    )


def test_commitment_claim_citing_supporting_evidence_kept():
    ctx = _context(["E1", "E2"], [_commitment_context(supporting=["E1"], conflicting=[])])
    claim = Claim(text="approved", citation_ids=["E1"], claim_type="commitment", commitment_context_id="C1")
    valid, _ = validate_and_filter_claims([claim], ctx)
    assert valid == [claim]


def test_commitment_claim_citing_supporting_and_conflicting_together_kept():
    ctx = _context(["E1", "E2"], [_commitment_context(supporting=["E1"], conflicting=["E2"])])
    claim = Claim(text="conflict", citation_ids=["E1", "E2"], claim_type="commitment", commitment_context_id="C1")
    valid, _ = validate_and_filter_claims([claim], ctx)
    assert valid == [claim]


def test_commitment_claim_citing_only_conflicting_evidence_dropped():
    """Conflicting evidence alone must never prove a commitment's authority/status."""
    ctx = _context(["E1", "E2"], [_commitment_context(supporting=["E1"], conflicting=["E2"])])
    claim = Claim(text="approved", citation_ids=["E2"], claim_type="commitment", commitment_context_id="C1")
    valid, summary = validate_and_filter_claims([claim], ctx)
    assert valid == []
    assert summary.claims_dropped == 1


def test_commitment_claim_citing_evidence_from_a_different_commitment_dropped():
    commitments = [
        _commitment_context(supporting=["E1"], conflicting=[]),
        CommitmentContext("C2", 2, "s2", "sales_unapproved", "at_risk", ["E2"], []),
    ]
    ctx = _context(["E1", "E2"], commitments)
    claim = Claim(text="approved", citation_ids=["E2"], claim_type="commitment", commitment_context_id="C1")
    valid, _ = validate_and_filter_claims([claim], ctx)
    assert valid == []


def test_commitment_claim_citing_nonexistent_commitment_dropped():
    ctx = _context(["E1"], [_commitment_context(supporting=["E1"], conflicting=[])])
    claim = Claim(text="approved", citation_ids=["E1"], claim_type="commitment", commitment_context_id="C17")
    valid, summary = validate_and_filter_claims([claim], ctx)
    assert valid == []
    assert "C17" in summary.invalid_ids_seen


# --- render_answer -----------------------------------------------------------


def test_render_answer_joins_claims_with_citation_markers():
    claims = [
        Claim(text="First fact.", citation_ids=["E1"], claim_type="evidence"),
        Claim(text="Second fact.", citation_ids=["E1", "E2"], claim_type="evidence"),
    ]
    assert render_answer(claims) == "First fact. [E1] Second fact. [E1][E2]"
