from datetime import datetime

from pydantic import BaseModel


class ChunkOut(BaseModel):
    id: int
    source: str
    title: str
    sensitivity: str
    occurred_at: datetime
    content: str
