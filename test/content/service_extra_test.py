from types import SimpleNamespace
from uuid import uuid4

import pytest

from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException

from app.modules.content import service


def test_commit_and_refresh_conflict_raises_http():
    class DB:
        def commit(self):
            raise IntegrityError("x", {}, Exception())

        def refresh(self, entity):
            return None

        def rollback(self):
            return None

    with pytest.raises(HTTPException) as exc:
        service._commit_and_refresh(DB(), SimpleNamespace(), conflict_detail="conflict")
    assert exc.value.status_code == 409


def test_normalize_pagination_edges():
    assert service._normalize_pagination(-10, 0) == (0, 1)
    assert service._normalize_pagination(5, 1000)[1] == service.MAX_PAGE_SIZE


def test_get_all_periods_filters(monkeypatch):
    # prepare fake query
    periods = [SimpleNamespace(id=1, is_active=True, is_published=True, order=1)]

    class FakeQuery:
        def __init__(self, data):
            self.data = data

        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def offset(self, n):
            return self

        def limit(self, n):
            return self

        def all(self):
            return self.data

    fake_db = SimpleNamespace(query=lambda model: FakeQuery(periods))
    res = service.get_all_periods(fake_db, only_published=True, skip=0, limit=10)
    assert res == periods


def test_create_and_update_event(monkeypatch):
    event_payload = {"name": "E", "description": "D"}
    data = SimpleNamespace(**event_payload, model_dump=lambda exclude_none=False: event_payload)
    # monkeypatch _commit_and_refresh to return the event object
    monkeypatch.setattr(service, "_commit_and_refresh", lambda db, entity, conflict_detail=None: entity)

    # create_event should return an object with attributes from data
    created = service.create_event(SimpleNamespace(add=lambda x: None), data, updated_by="me")
    assert created.name == "E"

    # update_event: simulate get_event_by_id
    ev = SimpleNamespace(name="Old", version=1, updated_by=None)
    monkeypatch.setattr(service, "get_event_by_id", lambda db, eid, include_unpublished=True: ev)
    udata = SimpleNamespace(name="New", model_dump=lambda exclude_none=True: {"name": "New"})
    updated = service.update_event(None, uuid4(), udata, updated_by="me")
    assert updated.version == 2
    assert updated.updated_by == "me"
