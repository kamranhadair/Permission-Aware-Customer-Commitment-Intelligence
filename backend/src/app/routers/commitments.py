from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user_context
from app.permissions.resolver import CommitmentWithEvidence, UserContext, get_visible_account, get_visible_commitments
from app.schemas.chunk import ChunkOut
from app.schemas.commitment import CommitmentOut

router = APIRouter()


def _to_commitment_out(item: CommitmentWithEvidence) -> CommitmentOut:
    return CommitmentOut(
        id=item.id,
        statement=item.statement,
        promised_by=item.promised_by,
        promise_date=item.promise_date,
        delivery_date=item.delivery_date,
        authority=item.authority,
        status=item.status,
        supporting_evidence=[
            ChunkOut(
                id=c.id, source=c.source, title=c.title, sensitivity=c.sensitivity, occurred_at=c.occurred_at,
                content=c.content,
            )
            for c in item.supporting
        ],
        conflicting_evidence=[
            ChunkOut(
                id=c.id, source=c.source, title=c.title, sensitivity=c.sensitivity, occurred_at=c.occurred_at,
                content=c.content,
            )
            for c in item.conflicting
        ],
    )


@router.get("/accounts/{account_slug}/commitments", response_model=list[CommitmentOut])
def list_commitments(
    account_slug: str,
    user_ctx: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db),
) -> list[CommitmentOut]:
    account = get_visible_account(db, user_ctx, account_slug)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    commitments = get_visible_commitments(db, user_ctx, account.id)
    return [_to_commitment_out(item) for item in commitments]
