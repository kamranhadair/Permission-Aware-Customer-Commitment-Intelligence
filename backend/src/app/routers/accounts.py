from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user_context
from app.permissions.resolver import AccountView, UserContext, get_permitted_accounts, get_visible_account
from app.schemas.account import AccountOut

router = APIRouter()


def _to_account_out(account: AccountView) -> AccountOut:
    return AccountOut(id=account.slug, name=account.name)


@router.get("/accounts", response_model=list[AccountOut])
def list_accounts(
    user_ctx: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db),
) -> list[AccountOut]:
    accounts = get_permitted_accounts(db, user_ctx)
    return [_to_account_out(account) for account in accounts]


@router.get("/accounts/{account_slug}", response_model=AccountOut)
def get_account(
    account_slug: str,
    user_ctx: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db),
) -> AccountOut:
    account = get_visible_account(db, user_ctx, account_slug)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return _to_account_out(account)
