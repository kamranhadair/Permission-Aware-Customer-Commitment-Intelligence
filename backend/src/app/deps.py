from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.permissions.resolver import UserContext, get_user_context


def get_current_user_context(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    db: Session = Depends(get_db),
) -> UserContext:
    """The single place an HTTP request turns into an authorization principal.

    Identity is dev-only (a header) but group/org membership is always
    resolved from the database — the client is never trusted to assert
    its own roles or groups.
    """
    if x_user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-User-Id header")

    try:
        user_id = int(x_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid X-User-Id header") from exc

    user_ctx = get_user_context(db, user_id)
    if user_ctx is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown user")

    return user_ctx
