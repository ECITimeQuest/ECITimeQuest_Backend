from types import SimpleNamespace
from sqlalchemy.exc import IntegrityError
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.auth import service
from app.enums.enums import UserRole, SubscriptionPlan


def test_normalize_role():
    assert service._normalize_role(None) is None
    assert service._normalize_role(UserRole.ADMIN) == UserRole.ADMIN
    assert service._normalize_role("admin") == UserRole.ADMIN
    assert service._normalize_role(" USER ") == UserRole.USER
    assert service._normalize_role("invalid") is None


def test_raise_user_integrity_error_checks():
    # firebase_uid conflict
    exc = IntegrityError("stmt", {}, Exception("duplicate key value violates unique constraint firebase_uid"))
    with pytest.raises(HTTPException) as e:
        service._raise_user_integrity_error(exc)
    assert e.value.status_code == 409

    # email conflict
    exc2 = IntegrityError("stmt", {}, Exception("duplicate key value violates unique constraint email"))
    with pytest.raises(HTTPException) as e2:
        service._raise_user_integrity_error(exc2)
    assert e2.value.status_code == 409


def test_sync_existing_user_changes():
    user = SimpleNamespace(email="a@b", name="A", role=UserRole.USER)
    changed = service._sync_existing_user(user, "a@b", "A", None)
    assert not changed
    changed2 = service._sync_existing_user(user, "x@b", "B", UserRole.ADMIN)
    assert changed2


def test_commit_user_changes_calls_raise_on_integrity(monkeypatch):
    class DB:
        def commit(self):
            raise IntegrityError("s", {}, Exception("email"))

        def refresh(self, user):
            return None

        def rollback(self):
            return None

    u = SimpleNamespace()
    with pytest.raises(HTTPException):
        service._commit_user_changes(DB(), u)


def test_upsert_user_from_token_create_flow(monkeypatch):
    token = {"uid": "u1", "email": "e@x.com", "name": "Name", "role": "admin"}
    # no existing user by firebase
    monkeypatch.setattr(service, "get_user_by_firebase_uid", lambda db, uid: None)
    # no reconcile
    monkeypatch.setattr(service, "_reconcile_user_by_email", lambda db, fu, em, nm, rl: None)
    created = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(service, "create_user", lambda db, data: created)

    res = service.upsert_user_from_token(None, token)
    assert res is created


def test_upsert_missing_fields_raises():
    with pytest.raises(HTTPException):
        service.upsert_user_from_token(None, {"email": "e@x.com"})


def test_update_user_role_demote_last_admin(monkeypatch):
    user_id = uuid4()
    user = SimpleNamespace(id=user_id, role=UserRole.ADMIN)
    monkeypatch.setattr(service, "get_user_by_id", lambda db, uid: user)
    monkeypatch.setattr(service, "_count_admin_users", lambda db: 1)

    with pytest.raises(HTTPException) as exc:
        service.update_user_role(None, user_id, UserRole.USER)
    assert exc.value.status_code == 400


def test_update_user_subscription_invalid_plan():
    with pytest.raises(HTTPException):
        service.update_user_subscription(None, uuid4(), "gold")


def test_update_user_subscription_sets_lives(monkeypatch):
    user_id = uuid4()
    user = SimpleNamespace(id=user_id, subscription_plan=SubscriptionPlan.FREE)
    progress = SimpleNamespace(lives=1, lives_refill_at=123)
    monkeypatch.setattr(service, "get_user_by_id", lambda db, uid: user)
    class Q:
        def filter(self, *a, **k):
            return self

        def first(self):
            return progress

    monkeypatch.setattr(service, "_commit_user_changes", lambda db, u: u)
    class MockModel: user_id = None
    monkeypatch.setattr(service, "UserProgress", MockModel)

    # monkeypatch db.query used in function via passing fake db with query
    fake_db = SimpleNamespace(query=lambda model: Q())

    res = service.update_user_subscription(fake_db, user_id, SubscriptionPlan.PREMIUM)
    assert res.subscription_plan == SubscriptionPlan.PREMIUM
    assert progress.lives == 5
    assert progress.lives_refill_at is None
