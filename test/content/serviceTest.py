from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.content import service
from app.modules.content.schemas import TopicContextForAI


class FakeQuery:
    def __init__(self, result=None):
        self.result = result

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def offset(self, n):
        return self

    def limit(self, n):
        return self

    def first(self):
        return self.result

    def all(self):
        if isinstance(self.result, list):
            return self.result
        if self.result is None:
            return []
        return [self.result]


class FakeDB:
    def __init__(self, results=None, commit_raises=False):
        self.results = results or {}
        self.commit_called = False
        self.commit_raises = commit_raises

    def query(self, model):
        key = model.__name__
        return FakeQuery(self.results.get(key))

    def commit(self):
        self.commit_called = True
        if self.commit_raises:
            raise IntegrityError("insert", {}, Exception("dup"))

    def refresh(self, entity):
        return None

    def rollback(self):
        return None


def test_normalize_pagination():
    assert service._normalize_pagination(0, 10) == (0, 10)
    assert service._normalize_pagination(-5, 0) == (0, 1)
    assert service._normalize_pagination(5, 1000)[1] == service.MAX_PAGE_SIZE


def test_commit_and_refresh_conflict_raises_http():
    db = FakeDB(commit_raises=True)
    entity = SimpleNamespace()

    with pytest.raises(Exception) as excinfo:
        service._commit_and_refresh(db, entity, conflict_detail="conflict")
    assert hasattr(excinfo.value, "status_code") or isinstance(excinfo.value, IntegrityError)


def test_get_period_by_id_not_found_raises():
    db = FakeDB({"HistoricalPeriod": None})
    with pytest.raises(Exception) as excinfo:
        service.get_period_by_id(db, uuid4())
    assert getattr(excinfo.value, "status_code", None) == 404


def test_get_topic_context_for_ai_success_and_filters():
    # prepare topic with period published and events/figures
    from datetime import datetime
    import uuid

    def make_event(name, year, published=True):
        return SimpleNamespace(
            id=uuid.uuid4(),
            name=name,
            description=f"desc {name}",
            year=year,
            era_start_year=None,
            era_end_year=None,
            location=None,
            difficulty_hint=None,
            is_published=published,
            version=1,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

    def make_figure(name, published=True):
        return SimpleNamespace(
            id=uuid.uuid4(),
            name=name,
            role=None,
            biography=f"bio {name}",
            birth_year=None,
            death_year=None,
            difficulty_hint=None,
            is_published=published,
            version=1,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

    event_published = make_event("A", 1000, True)
    event_unpublished = make_event("B", 900, False)
    figure1 = make_figure("Z", True)
    figure2 = make_figure("A", True)

    period = SimpleNamespace(name="Era", is_published=True, is_active=True, id=uuid.uuid4(), order=0, start_year=None, end_year=None, version=1, created_at=datetime.utcnow(), updated_at=datetime.utcnow(), description="pdesc")
    topic = SimpleNamespace(
        id=uuid4(),
        name="Topic",
        description="Desc",
        difficulty=3,
        difficulty_hint="Hint",
        period=period,
        events=[event_unpublished, event_published],
        figures=[figure1, figure2],
    )

    db = FakeDB({"Topic": topic})

    # monkeypatch get_topic_by_id to return our topic
    original = service.get_topic_by_id
    service.get_topic_by_id = lambda db, tid: topic
    try:
        ctx = service.get_topic_context_for_ai(db, topic.id)
        assert isinstance(ctx, TopicContextForAI)
        assert ctx.topic_name == topic.name
        # events should include only the published one
        assert all(e.is_published for e in ctx.events)
        # figures should be sorted by name
        assert [f.name for f in ctx.figures] == sorted([figure1.name, figure2.name], key=lambda s: s.lower())
    finally:
        service.get_topic_by_id = original


def test_get_topic_context_for_ai_missing_period_raises():
    topic = SimpleNamespace(id=uuid4(), period=None)
    db = FakeDB({"Topic": topic})
    original = service.get_topic_by_id
    service.get_topic_by_id = lambda db, tid: topic
    try:
        with pytest.raises(Exception) as excinfo:
            service.get_topic_context_for_ai(db, topic.id)
        assert getattr(excinfo.value, "status_code", None) == 404
    finally:
        service.get_topic_by_id = original
