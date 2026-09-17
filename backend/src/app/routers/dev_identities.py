"""GET /dev/demo-users — dev/demo-only. Mounted only when
`settings.enable_demo_mode` is true (see app/main.py); otherwise this route
does not exist at all (a real 404, not a permission check on a live route).

This lets a frontend demo-user switcher discover *currently valid* X-User-Id
values without hardcoding database-generated ids, which are not stable
across a reseed. It intentionally returns nothing beyond presentation-safe
fields — no group membership, no org id, no ACL rows, no permitted-resource
counts. It is not a general user-directory API: it only ever resolves the
single "Demo Org" (see app/demo/org.py), and fails closed rather than
guessing if that resolution is ambiguous.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.demo.org import AmbiguousDemoOrgError, list_demo_users
from app.schemas.demo import DemoUserOut

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/dev/demo-users", response_model=list[DemoUserOut])
def get_demo_users(db: Session = Depends(get_db)) -> list[DemoUserOut]:
    try:
        users = list_demo_users(db)
    except AmbiguousDemoOrgError as exc:
        # Conflicting org ids are logged server-side only — never put them
        # in the HTTP response body.
        logger.error("ambiguous Demo Org: %s", exc.org_ids)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Demo environment misconfigured",
        ) from None

    return [DemoUserOut(id=u.id, name=u.display_name, email=u.email, label=u.role) for u in users]
