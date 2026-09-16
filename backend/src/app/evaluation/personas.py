"""Shared persona/org/account seeding for the Milestone 6 evaluation
runner. Supersedes the near-duplicate `_seed()` in the retired
`retrieval/evaluate.py` and `generation/evaluate.py` scripts — one seed
routine, reused by all three evaluation modes.

Personas cover every permission condition the golden dataset needs
(section 2 of the Milestone 6 design):
- alice:  account-management group only
- bob:    product group only
- carol:  product + exec groups
- dana:   account-management + product groups (the "sees both sides" persona)
- erin:   NO group membership at all — direct per-document ACL grants only
- frank:  a user in a SEPARATE organization, used only to prove cross-org
          isolation (frank must never see anything from the eval org)

Group-membership/document-ACL revocation for permission-freshness cases is
NOT done here — see `freshness.py`, which mutates and then restores rows
against an already-seeded database so it can never leak into other cases.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Account, Group, GroupMembership, Organization, User

EVAL_ORG_NAME = "Evaluation Org"
CROSS_ORG_NAME = "Evaluation Org (Cross-Org)"

ACCOUNT_SLUGS = ("acme-corp", "globex-inc", "initech-ltd", "injection-test-co")

PERSONA_GROUPS: dict[str, tuple[str, ...]] = {
    "alice": ("account-management",),
    "bob": ("product",),
    "carol": ("product", "exec"),
    "dana": ("account-management", "product"),
    "erin": (),
}


@dataclass(frozen=True)
class EvalSeed:
    org: Organization
    cross_org: Organization
    accounts: dict[str, Account]
    users: dict[str, User]
    groups: dict[str, Group]


def seed(db: Session) -> EvalSeed:
    org = Organization(name=EVAL_ORG_NAME)
    cross_org = Organization(name=CROSS_ORG_NAME)
    db.add_all([org, cross_org])
    db.flush()

    accounts = {}
    for slug in ACCOUNT_SLUGS:
        account = Account(org_id=org.id, slug=slug, name=slug)
        db.add(account)
        accounts[slug] = account
    db.flush()

    groups = {}
    for name in ("account-management", "product", "exec"):
        group = Group(org_id=org.id, name=name)
        db.add(group)
        groups[name] = group
    db.flush()

    users = {}
    for name in ("alice", "bob", "carol", "dana", "erin"):
        user = User(org_id=org.id, email=f"{name}@vendor.example", display_name=name)
        db.add(user)
        users[name] = user
    # frank belongs to the cross-org — never a member of any eval-org group,
    # never granted any eval-org document ACL.
    frank = User(org_id=cross_org.id, email="frank@othervendor.example", display_name="frank")
    db.add(frank)
    users["frank"] = frank
    db.flush()

    for name, group_names in PERSONA_GROUPS.items():
        for group_name in group_names:
            db.add(GroupMembership(user_id=users[name].id, group_id=groups[group_name].id))
    db.commit()

    return EvalSeed(org=org, cross_org=cross_org, accounts=accounts, users=users, groups=groups)
