from types import SimpleNamespace
from uuid import uuid4

import pytest

from fastapi import HTTPException

from app.modules.content import service
from app.modules.content.schemas import HistoricalPeriodUpdate, TopicCreate


def test_add_event_to_topic_conflict(monkeypatch):
    topic = SimpleNamespace(events=[], id=uuid4())
    event = SimpleNamespace()
    # make event already in topic
    topic.events.append(event)

    monkeypatch.setattr(service, "get_topic_by_id", lambda db, tid, include_unpublished=True: topic)
    monkeypatch.setattr(service, "get_event_by_id", lambda db, eid, include_unpublished=True: event)

    with pytest.raises(HTTPException) as exc:
        service.add_event_to_topic(None, uuid4(), uuid4())
    assert exc.value.status_code == 409


def test_remove_event_from_topic_not_linked(monkeypatch):
    topic = SimpleNamespace(events=[], id=uuid4())
    event = SimpleNamespace()

    monkeypatch.setattr(service, "get_topic_by_id", lambda db, tid, include_unpublished=True: topic)
    monkeypatch.setattr(service, "get_event_by_id", lambda db, eid, include_unpublished=True: event)

    with pytest.raises(HTTPException) as exc:
        service.remove_event_from_topic(None, uuid4(), uuid4())
    assert exc.value.status_code == 404


def test_add_and_remove_figure_conflict(monkeypatch):
    figure = SimpleNamespace()
    topic = SimpleNamespace(figures=[figure], id=uuid4())

    monkeypatch.setattr(service, "get_topic_by_id", lambda db, tid, include_unpublished=True: topic)
    monkeypatch.setattr(service, "get_figure_by_id", lambda db, fid, include_unpublished=True: figure)

    with pytest.raises(HTTPException):
        service.add_figure_to_topic(None, uuid4(), uuid4())

    # now test remove works when not linked
    topic2 = SimpleNamespace(figures=[], id=uuid4())
    monkeypatch.setattr(service, "get_topic_by_id", lambda db, tid, include_unpublished=True: topic2)
    with pytest.raises(HTTPException):
        service.remove_figure_from_topic(None, uuid4(), uuid4())


def test_update_period_increments_version(monkeypatch):
    period = SimpleNamespace(id=uuid4(), version=1, updated_by=None, name="old")
    monkeypatch.setattr(service, "get_period_by_id", lambda db, pid, include_unpublished=True: period)
    # make commit return the same object
    monkeypatch.setattr(service, "_commit_and_refresh", lambda db, entity, conflict_detail=None: entity)

    data = HistoricalPeriodUpdate(name="new")
    res = service.update_period(None, period.id, data, updated_by="me")
    assert res.version == 2
    assert res.updated_by == "me"
    assert res.name == "new"


def test_create_topic_calls_get_period(monkeypatch):
    # Ensure get_period_by_id is called
    called = {}

    def fake_get_period(db, pid, include_unpublished=True):
        called['ok'] = True
        return SimpleNamespace()

    monkeypatch.setattr(service, "get_period_by_id", fake_get_period)
    monkeypatch.setattr(service, "_commit_and_refresh", lambda db, entity, conflict_detail=None: entity)

    data = TopicCreate(period_id=uuid4(), name="T", description="D", difficulty=1)
    fake_db = SimpleNamespace(add=lambda x: None)
    res = service.create_topic(fake_db, data, updated_by="me")
    assert called.get('ok', False)
    assert res.name == "T"


def test_get_challenges_by_topic(monkeypatch):
    # monkeypatch get_topic_by_id to succeed
    monkeypatch.setattr(service, "get_topic_by_id", lambda db, tid, include_unpublished=True: True)

    # fake DB query returning challenges
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

    fake_challenges = [SimpleNamespace(id=uuid4(), topic_id=uuid4(), is_active=True, is_published=True)]
    fake_db = SimpleNamespace(query=lambda model: FakeQuery(fake_challenges))

    res = service.get_challenges_by_topic(fake_db, uuid4())
    assert res == fake_challenges
