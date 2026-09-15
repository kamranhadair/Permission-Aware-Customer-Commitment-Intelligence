from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user_context
from app.permissions.resolver import ChunkView, UserContext, get_permitted_chunks, get_visible_account
from app.schemas.chunk import ChunkOut

router = APIRouter()


def _to_chunk_out(chunk: ChunkView) -> ChunkOut:
    return ChunkOut(
        id=chunk.id,
        source=chunk.source,
        title=chunk.title,
        sensitivity=chunk.sensitivity,
        occurred_at=chunk.occurred_at,
        content=chunk.content,
    )


@router.get("/accounts/{account_slug}/chunks", response_model=list[ChunkOut])
def list_chunks(
    account_slug: str,
    user_ctx: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db),
) -> list[ChunkOut]:
    account = get_visible_account(db, user_ctx, account_slug)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    chunks = get_permitted_chunks(db, user_ctx, account.id)
    return [_to_chunk_out(chunk) for chunk in chunks]
