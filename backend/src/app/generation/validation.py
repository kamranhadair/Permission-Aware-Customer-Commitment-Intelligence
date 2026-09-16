"""Two validation layers, deliberately kept separate:

1. Schema validation (`parse_provider_payload`): is the provider's raw tool
   payload even shaped like a GeneratedAnswer? A forced tool call lowers
   the risk of malformed output but does not remove the need to check it —
   this is where that check happens, always, before anything downstream
   trusts the payload. Failure here is a GenerationFailure (provider/schema
   problem), never a business-level "insufficient evidence" outcome.

2. Grounding validation (`validate_and_filter_claims`): given a
   schema-valid GeneratedAnswer, which of its claims are actually grounded
   in the supplied context? A claim can be well-formed and still cite an
   unknown id, a [Cn] internal label, evidence belonging to a different
   commitment, or (for a "commitment" claim) only conflicting evidence with
   no supporting evidence at all — none of these prove the claim's
   authority/status assertion. Invalid claims are dropped individually;
   whether *zero surviving claims* is a failure or a legitimate abstention
   is a decision made by the caller (see generation/service.py), not here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.generation.errors import GenerationFailure
from app.generation.types import Claim, GeneratedAnswer, GenerationContext


class RawClaim(BaseModel):
    text: str
    citation_ids: list[str] = Field(default_factory=list)
    claim_type: Literal["evidence", "commitment"]
    commitment_context_id: str | None = None


class RawGeneratedAnswer(BaseModel):
    """The wire-format contract for the submit_answer tool payload. Its
    JSON schema (`RawGeneratedAnswer.model_json_schema()`) is reused
    directly as the tool's `input_schema` in provider.py, so the schema we
    validate against can never drift from the schema we asked the model to
    produce."""

    status: Literal["answered", "insufficient_evidence"]
    claims: list[RawClaim] = Field(default_factory=list)


def parse_provider_payload(payload: dict) -> GeneratedAnswer:
    try:
        raw = RawGeneratedAnswer.model_validate(payload)
    except ValidationError as exc:
        raise GenerationFailure(f"provider payload failed schema validation: {exc}") from exc

    claims = [
        Claim(
            text=c.text,
            citation_ids=list(c.citation_ids),
            claim_type=c.claim_type,
            commitment_context_id=c.commitment_context_id,
        )
        for c in raw.claims
    ]
    return GeneratedAnswer(status=raw.status, claims=claims)


@dataclass(frozen=True)
class ValidationSummary:
    invalid_ids_seen: list[str]
    claims_dropped: int


def validate_and_filter_claims(
    claims: list[Claim], context: GenerationContext
) -> tuple[list[Claim], ValidationSummary]:
    valid_evidence_ids = {chunk.citation_id for chunk in context.evidence}
    commitments_by_id = {commitment.citation_id: commitment for commitment in context.commitments}

    valid_claims: list[Claim] = []
    invalid_ids_seen: list[str] = []

    for claim in claims:
        if not claim.citation_ids:
            continue  # unsupported claim — no citation at all

        unknown_ids = [cid for cid in claim.citation_ids if cid not in valid_evidence_ids]
        if unknown_ids:
            # Covers both invented ids (e.g. "E17") and [Cn] ids misused as
            # citations — [Cn] is never a member of valid_evidence_ids.
            invalid_ids_seen.extend(unknown_ids)
            continue

        if claim.claim_type == "evidence":
            if claim.commitment_context_id is not None:
                continue  # malformed combination — drop defensively
            valid_claims.append(claim)
            continue

        # claim_type == "commitment"
        commitment = commitments_by_id.get(claim.commitment_context_id or "")
        if commitment is None:
            invalid_ids_seen.append(claim.commitment_context_id or "<missing commitment_context_id>")
            continue

        allowed_ids = set(commitment.supporting_citation_ids) | set(commitment.conflicting_citation_ids)
        cited_ids = set(claim.citation_ids)
        if not cited_ids <= allowed_ids:
            continue  # cites evidence outside this commitment's own provenance

        if not (cited_ids & set(commitment.supporting_citation_ids)):
            continue  # conflicting evidence alone cannot prove the commitment's authority/status

        valid_claims.append(claim)

    summary = ValidationSummary(invalid_ids_seen=invalid_ids_seen, claims_dropped=len(claims) - len(valid_claims))
    return valid_claims, summary


def render_answer(claims: list[Claim]) -> str:
    sentences = []
    for claim in claims:
        markers = "".join(f"[{cid}]" for cid in claim.citation_ids)
        sentences.append(f"{claim.text.strip()} {markers}".strip())
    return " ".join(sentences)
