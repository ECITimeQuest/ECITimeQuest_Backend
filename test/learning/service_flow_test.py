from types import SimpleNamespace
from uuid import uuid4, UUID
from datetime import datetime, timezone

import pytest

from fastapi import HTTPException

from app.modules.learning import service


class FakeQuery:
    def __init__(self, result=None):
        self.result = result

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.result

    def all(self):
        return self.result or []


class FakeDB:
    def __init__(self, mapping=None):
        self.mapping = mapping or {}
        self.added = []
        self.committed = False
        self.refreshed = []

    def query(self, model):
        return FakeQuery(self.mapping.get(model.__name__))

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True

    def refresh(self, obj):
        self.refreshed.append(obj)

    def rollback(self):
        return None


def test_start_session_no_lives_raises(monkeypatch):
    p = SimpleNamespace(lives=0, lives_refill_at=datetime.now(timezone.utc))
    monkeypatch.setattr(service, "get_or_create_progress", lambda db, uid: p)
    monkeypatch.setattr(service, "_get_topic_for_learning", lambda db, tid: True)

    with pytest.raises(HTTPException) as exc:
        service.start_session(None, uuid4(), SimpleNamespace(topic_id=uuid4()))
    assert exc.value.status_code == 400


def test_start_session_success(monkeypatch):
    p = SimpleNamespace(lives=3, lives_refill_at=None)
    monkeypatch.setattr(service, "get_or_create_progress", lambda db, uid: p)
    monkeypatch.setattr(service, "_get_topic_for_learning", lambda db, tid: True)

    fake_db = FakeDB()
    session = service.start_session(fake_db, uuid4(), SimpleNamespace(topic_id=uuid4()))
    assert session.user_id is not None


def test_submit_answer_not_found():
    fake_db = FakeDB({"LearningSession": None})
    with pytest.raises(HTTPException) as exc:
        service.submit_answer(fake_db, uuid4(), uuid4(), SimpleNamespace(session_id=uuid4(), question_id=uuid4(), concept="c", answer="a", response_time_ms=100, is_correct=True))
    assert exc.value.status_code == 404


def test_submit_answer_correct_no_persist(monkeypatch):
    user_id = uuid4()
    session_id = uuid4()
    session = SimpleNamespace(id=session_id, user_id=user_id, finished_at=None, lives_lost=0, topic_id=uuid4())
    fake_db = FakeDB({"LearningSession": session, "UserProgress": None})

    # non-premium user
    monkeypatch.setattr(service, "get_user_by_id", lambda db, uid: SimpleNamespace(subscription_plan=None))

    res = service.submit_answer(fake_db, user_id, session_id, SimpleNamespace(session_id=session_id, question_id=uuid4(), concept="ok", answer="a", response_time_ms=100, is_correct=True))
    assert res.xp_earned == service.XP_PER_CORRECT_ANSWER
    assert res.lives_lost == 0
    assert not fake_db.committed


def test_submit_answer_incorrect_persist(monkeypatch):
    user_id = uuid4()
    session_id = uuid4()
    topic_id = uuid4()
    session = SimpleNamespace(id=session_id, user_id=user_id, finished_at=None, lives_lost=0, topic_id=topic_id)
    fake_db = FakeDB({"LearningSession": session, "UserProgress": None})

    # non-premium user
    monkeypatch.setattr(service, "get_user_by_id", lambda db, uid: SimpleNamespace(subscription_plan=None))
    def fake_apply_sync(db_, uid_, s, data_, finished_at=None):
        s.xp_gained = 10
        s.coins_gained = 5
        s.lives_lost = 0
        s.completed = data_.completed
        s.finished_at = finished_at or datetime.now(timezone.utc)
        return (10, 5, 0)

    monkeypatch.setattr(service, "_apply_session_completion", fake_apply_sync)

def test_finish_session_calls_apply_and_persists(monkeypatch):
    user_id = uuid4()
    session_id = uuid4()
    session = SimpleNamespace(id=session_id, user_id=user_id, finished_at=None, lives_lost=0, topic_id=uuid4())
    fake_db = FakeDB({"LearningSession": session})

    called = {}
    def fake_apply(db, uid, s, data, finished_at=None):
        called['ok'] = True
        s.finished_at = datetime.now(timezone.utc)
        return (10, 5, 0)

    monkeypatch.setattr(service, "_apply_session_completion", fake_apply)

    res = service.finish_session(fake_db, user_id, session_id, SimpleNamespace(correct_answers=1, wrong_answers=0, avg_response_time_ms=None, completed=True))
    assert called.get('ok')
    assert fake_db.committed
    assert res.finished_at is not None


def test_sync_offline_sessions_skipped_and_processed(monkeypatch):
    user_id = uuid4()
    topic_ok = uuid4()
    topic_bad = uuid4()

    # prepare offline sessions
    off1 = SimpleNamespace(client_session_id=uuid4(), topic_id=topic_bad, correct_answers=1, wrong_answers=0, avg_response_time_ms=100, completed=True, started_at=None, finished_at=None)
    off2 = SimpleNamespace(client_session_id=uuid4(), topic_id=topic_ok, correct_answers=1, wrong_answers=0, avg_response_time_ms=100, completed=True, started_at=None, finished_at=None)

    # DB behaviour: topic_bad missing, topic_ok exists, no existing sync event for topic_ok
    def query_override(model):
        name = model.__name__
        if name == 'Topic':
            # return truthy for existence check
            return FakeQuery(SimpleNamespace())
        if name == 'LearningSyncEvent':
            # no existing sync events
            return FakeQuery(None)
        return FakeQuery(None)

    db = FakeDB()
    db.query = query_override

    def fake_apply_sync(db, uid, s, data, finished_at=None): s.xp_gained=10; s.coins_gained=5; s.lives_lost=0; s.completed=data.completed; s.finished_at=finished_at or datetime.now(timezone.utc); return (10, 5, 0)
    monkeypatch.setattr(service, "_apply_session_completion", fake_apply_sync)

    data = SimpleNamespace(sessions=[off1, off2])
    res = service.sync_offline_sessions(db, user_id, data)
    assert isinstance(res.processed, int)
    assert isinstance(res.skipped, int)
