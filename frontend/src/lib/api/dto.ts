// Backend response shapes, mirroring backend/src/app/schemas/*.py exactly
// (field names as FastAPI actually serializes them — snake_case). Kept
// separate from src/types/domain.ts on purpose: these are the wire
// contract, not what components render. See src/lib/mapping.ts for the
// DTO -> view-model boundary.

export type AccountDTO = {
  id: string;
  name: string;
};

export type ChunkDTO = {
  id: number;
  source: string;
  title: string;
  sensitivity: string;
  occurred_at: string;
  content: string;
};

export type CommitmentDTO = {
  id: number;
  statement: string;
  promised_by: string;
  promise_date: string;
  delivery_date: string | null;
  authority: string;
  status: string;
  supporting_evidence: ChunkDTO[];
  conflicting_evidence: ChunkDTO[];
};

export type DemoUserDTO = {
  id: number;
  name: string;
  email: string;
  label: string | null;
};

export type RetrievalHitDTO = {
  chunk_id: number;
  document_id: number;
  account_id: number;
  source: string;
  title: string;
  content: string;
  occurred_at: string;
  lexical_rank: number | null;
  vector_rank: number | null;
  hybrid_score: number;
};

export type SearchResponseDTO = {
  results: RetrievalHitDTO[];
  // Intentionally untyped/ignored: Milestone 7 does not turn the backend's
  // retrieval trace into a product feature (see docs/architecture.md).
  trace?: unknown;
};

export type CitationDTO = {
  citation_id: string;
  chunk_id: number;
  document_id: number;
  source: string;
  title: string;
  occurred_at: string;
  excerpt: string;
};

export type AnswerResponseDTO = {
  answer: string;
  status: "answered" | "insufficient_evidence";
  citations: CitationDTO[];
  trace?: unknown;
};
