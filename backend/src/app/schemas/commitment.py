from datetime import date

from pydantic import BaseModel

from app.schemas.chunk import ChunkOut


class CommitmentOut(BaseModel):
    id: int
    statement: str
    promised_by: str
    promise_date: date
    delivery_date: date | None
    authority: str
    status: str
    supporting_evidence: list[ChunkOut]
    conflicting_evidence: list[ChunkOut]
