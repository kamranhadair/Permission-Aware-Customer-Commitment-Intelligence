// Backend DTO -> frontend view model. The security-sensitive distinction
// this file exists to make obvious: the backend DTO may contain only
// evidence the resolver already decided the caller may see — these
// functions never filter, never inspect sensitivity/ACL fields (they
// aren't present in the DTOs at all), and never decide what's permitted.
// They only reshape already-permitted data for rendering.

import type {
  AccountDTO,
  ChunkDTO,
  CitationDTO,
  CommitmentDTO,
  DemoUserDTO,
  RetrievalHitDTO,
} from "./api/dto.ts";
import type {
  AccountView,
  CitationView,
  CommitmentAuthority,
  CommitmentStatus,
  CommitmentView,
  DemoUserView,
  EvidenceSource,
  EvidenceView,
  RetrievalHitView,
} from "../types/domain.ts";

export function mapAccount(dto: AccountDTO): AccountView {
  return { id: dto.id, name: dto.name };
}

export function mapEvidence(dto: ChunkDTO): EvidenceView {
  return {
    id: String(dto.id),
    source: dto.source as EvidenceSource,
    title: dto.title,
    excerpt: dto.content,
    occurredAt: dto.occurred_at,
  };
}

export function mapCommitment(dto: CommitmentDTO): CommitmentView {
  return {
    id: String(dto.id),
    statement: dto.statement,
    promisedBy: dto.promised_by,
    promiseDate: dto.promise_date,
    deliveryDate: dto.delivery_date ?? undefined,
    authority: dto.authority as CommitmentAuthority,
    status: dto.status as CommitmentStatus,
    supportingEvidence: dto.supporting_evidence.map(mapEvidence),
    conflictingEvidence: dto.conflicting_evidence.map(mapEvidence),
  };
}

export function mapCitation(dto: CitationDTO): CitationView {
  return {
    id: String(dto.chunk_id),
    citationLabel: dto.citation_id,
    source: dto.source as EvidenceSource,
    title: dto.title,
    excerpt: dto.excerpt,
    occurredAt: dto.occurred_at,
  };
}

export function mapDemoUser(dto: DemoUserDTO): DemoUserView {
  return { id: dto.id, name: dto.name, email: dto.email, label: dto.label };
}

export function mapRetrievalHit(dto: RetrievalHitDTO): RetrievalHitView {
  return {
    chunkId: String(dto.chunk_id),
    documentId: String(dto.document_id),
    source: dto.source as EvidenceSource,
    title: dto.title,
    content: dto.content,
    occurredAt: dto.occurred_at,
  };
}
