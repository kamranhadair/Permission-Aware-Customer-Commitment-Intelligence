"""Resolves the single persistent "Demo Org" by name.

`Organization` has no unique/slug column (see app/models/org.py), so
resolving "the" demo org by name is an application-level invariant, not a
database constraint. Both the read-only `GET /dev/demo-users` endpoint
(app/routers/dev_identities.py) and the seed script (app/demo/seed.py)
import this single function rather than each writing their own
`.first()`-style lookup, so the fail-closed behavior only needs to be
correct — and tested — once.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Organization, User

DEMO_ORG_NAME = "Demo Org"


class AmbiguousDemoOrgError(RuntimeError):
    """More than one Organization is named DEMO_ORG_NAME. Picking one
    arbitrarily (e.g. via `.first()`) could silently expose or attribute
    demo data to the wrong row, so callers must treat this as a
    configuration error, never guess. Conflicting ids are attached for
    server-side logging only — callers must never put them in an HTTP
    response body.
    """

    def __init__(self, org_ids: list[int]):
        super().__init__(f"{len(org_ids)} organizations named {DEMO_ORG_NAME!r} exist: {org_ids}")
        self.org_ids = org_ids


def resolve_demo_org(db: Session) -> Organization | None:
    """None means the demo org hasn't been seeded yet — a safe, expected
    state (e.g. GET /dev/demo-users should return an empty list, not an
    error). Raises AmbiguousDemoOrgError if more than one row matches.
    """
    orgs = list(db.scalars(select(Organization).where(Organization.name == DEMO_ORG_NAME)))
    if not orgs:
        return None
    if len(orgs) > 1:
        raise AmbiguousDemoOrgError([o.id for o in orgs])
    return orgs[0]


def list_demo_users(db: Session) -> list[User]:
    """Every user in the resolved Demo Org, or [] if it hasn't been seeded
    yet. The one query app/routers/dev_identities.py needs — kept here
    (not inline in the router) so that router can stay a thin HTTP/DTO
    layer with no direct model/SQLAlchemy access of its own, matching
    every other router in this codebase (see tests/test_architecture.py).
    """
    org = resolve_demo_org(db)  # raises AmbiguousDemoOrgError; not caught here
    if org is None:
        return []
    return list(db.scalars(select(User).where(User.org_id == org.id).order_by(User.id)))
