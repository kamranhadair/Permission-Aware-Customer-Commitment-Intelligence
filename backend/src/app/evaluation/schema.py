"""Pydantic models validating the golden dataset / permission-freshness
sequence files at load time — fail fast on a malformed case rather than
discovering it mid-run.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

Category = Literal[
    "direct_lookup",
    "cross_doc_synthesis",
    "conflicting_evidence",
    "temporal",
    "permission_refusal",
    "commitment_authority",
    "prompt_injection",
    "insufficient_evidence",
]

# "account_not_visible" is not an AnswerResult.status value — it means
# answer()/retrieve() returned None (the account itself 404s for this
# persona), a structurally different outcome from "answered" with empty
# evidence.
ExpectedStatus = Literal["answered", "insufficient_evidence", "account_not_visible"]

StructuralCheck = Literal[
    "no_invented_citation",
    "context_scoped_to_account",
    "no_reserved_authority_word_without_commitment",
]


class StableEvidenceRef(BaseModel):
    source: str
    external_id: str


class GoldenCase(BaseModel):
    id: str
    category: Category
    persona: str
    account_slug: str
    query: str
    retrieval_only: bool = False
    expected_status: ExpectedStatus
    acceptable_statuses: list[ExpectedStatus] | None = None
    expected_evidence: list[StableEvidenceRef] = Field(default_factory=list)
    forbidden_evidence: list[StableEvidenceRef] = Field(default_factory=list)
    expected_authority: str | None = None
    expected_conflict: bool | None = None
    expected_temporal_precedence: StableEvidenceRef | None = None
    structural_checks: list[StructuralCheck] = Field(default_factory=list)
    manual_review_only: list[str] = Field(default_factory=list)
    note: str | None = None  # privileged, evaluator-only — see stable_ids.py docstring

    def statuses_ok(self) -> set[str]:
        return set(self.acceptable_statuses) if self.acceptable_statuses else {self.expected_status}


class GoldenDataset(BaseModel):
    cases: list[GoldenCase]

    @model_validator(mode="after")
    def _unique_ids(self) -> "GoldenDataset":
        ids = [c.id for c in self.cases]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"duplicate golden case ids: {sorted(dupes)}")
        return self


MutationAction = Literal["revoke_group_membership", "grant_group_membership", "revoke_document_acl"]


class QueryStep(BaseModel):
    kind: Literal["query"]
    t: str
    persona: str
    account_slug: str
    query: str
    expected_status: ExpectedStatus
    acceptable_statuses: list[ExpectedStatus] | None = None
    expected_evidence: list[StableEvidenceRef] = Field(default_factory=list)
    forbidden_evidence: list[StableEvidenceRef] = Field(default_factory=list)

    def statuses_ok(self) -> set[str]:
        return set(self.acceptable_statuses) if self.acceptable_statuses else {self.expected_status}


class MutateStep(BaseModel):
    kind: Literal["mutate"]
    action: MutationAction
    persona: str
    group: str | None = None
    account_slug: str | None = None  # required for revoke_document_acl
    source: str | None = None
    external_id: str | None = None


class FreshnessSequence(BaseModel):
    id: str
    steps: list[QueryStep | MutateStep]


class FreshnessDataset(BaseModel):
    sequences: list[FreshnessSequence]

    @model_validator(mode="after")
    def _unique_ids(self) -> "FreshnessDataset":
        ids = [s.id for s in self.sequences]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"duplicate sequence ids: {sorted(dupes)}")
        return self
