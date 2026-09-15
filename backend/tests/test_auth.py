from tests.factories import make_org, make_user


def test_missing_user_header_is_rejected(client):
    resp = client.get("/accounts")
    assert resp.status_code == 401


def test_unknown_user_is_rejected(db, client):
    make_org(db)  # org/user rows exist, but not for id 999999
    resp = client.get("/accounts", headers={"X-User-Id": "999999"})
    assert resp.status_code == 401


def test_non_integer_user_header_is_rejected(client):
    resp = client.get("/accounts", headers={"X-User-Id": "not-a-number"})
    assert resp.status_code == 401


def test_known_user_is_accepted(db, client):
    org = make_org(db)
    user = make_user(db, org, "u1@x.com")

    resp = client.get("/accounts", headers={"X-User-Id": str(user.id)})
    assert resp.status_code == 200
