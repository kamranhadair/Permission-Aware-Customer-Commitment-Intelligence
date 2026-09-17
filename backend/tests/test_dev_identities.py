"""GET /dev/demo-users: mounted only when demo mode is enabled, returns
only presentation-safe fields, and fails closed (never guesses) if more
than one "Demo Org" row exists.
"""

from fastapi.testclient import TestClient

from app.db import get_db
from app.demo.org import DEMO_ORG_NAME
from app.main import create_app
from app.models import Organization, User


def _client(db, *, enable_demo_mode: bool) -> TestClient:
    app = create_app(enable_demo_mode=enable_demo_mode)

    def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)


def test_route_not_mounted_when_demo_mode_disabled(db):
    client = _client(db, enable_demo_mode=False)
    resp = client.get("/dev/demo-users")
    assert resp.status_code == 404


def test_empty_list_when_no_demo_org_seeded(db):
    client = _client(db, enable_demo_mode=True)
    resp = client.get("/dev/demo-users")
    assert resp.status_code == 200
    assert resp.json() == []


def test_returns_only_presentation_safe_fields(db):
    org = Organization(name=DEMO_ORG_NAME)
    db.add(org)
    db.flush()
    user = User(org_id=org.id, email="maya@demo.example", display_name="Maya Chen", role="Account Manager")
    db.add(user)
    db.flush()

    client = _client(db, enable_demo_mode=True)
    resp = client.get("/dev/demo-users")
    assert resp.status_code == 200
    body = resp.json()
    assert body == [
        {"id": user.id, "name": "Maya Chen", "email": "maya@demo.example", "label": "Account Manager"}
    ]
    # No group/org/ACL-shaped keys on the item at all, not merely empty ones.
    assert set(body[0].keys()) == {"id", "name", "email", "label"}


def test_fails_closed_on_ambiguous_demo_org(db):
    org_a = Organization(name=DEMO_ORG_NAME)
    org_b = Organization(name=DEMO_ORG_NAME)
    db.add_all([org_a, org_b])
    db.flush()
    ids = (org_a.id, org_b.id)

    client = _client(db, enable_demo_mode=True)
    resp = client.get("/dev/demo-users")
    assert resp.status_code == 500
    body_text = resp.text
    for org_id in ids:
        assert str(org_id) not in body_text
