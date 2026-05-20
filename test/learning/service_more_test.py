from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.learning import service
from app.modules.learning.schemas import ConceptGapCreate
from fastapi import HTTPException


class FakeQuery:
    def __init__(self, result=None):
        self.result = result

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, n):
        return self

    def first(self):
        return self.result if not isinstance(self.result, list) else (self.result[0] if self.result else None)

    def all(self):
        if isinstance(self.result, list):
            return self.result
        if self.result is None:
            return []
        return [self.result]


class FakeDB:
    def __init__(self, mapping=None):
        self.mapping = mapping or {}
        self.added = []
        self.deleted = []
        self.committed = False

    def query(self, model):
        return FakeQuery(self.mapping.get(model.__name__))

    def add(self, obj):
        self.added.append(obj)

    def delete(self, obj):
        self.deleted.append(obj)

    def commit(self):
        self.committed = True

    def refresh(self, obj):
        return None

    def rollback(self):
        return None


def test_get_learning_context_for_ai():
    progress = SimpleNamespace(level=4)
    gaps = [SimpleNamespace(concept="x", weakness_score=0.75), SimpleNamespace(concept="y", weakness_score=0.5)]
    db = FakeDB({"UserProgress": progress, "ConceptGap": gaps})

    res = service.get_learning_context_for_ai(db, uuid4(), uuid4())
    assert res["user_level"] == 4
    assert "Severity" in res["concept_gaps"][0]


def test_spend_coins_insufficient_and_success(monkeypatch):
    # insufficient
    progress_low = SimpleNamespace(coins=5)
    monkeypatch.setattr(service, "get_or_create_progress", lambda db, uid: progress_low)
    with pytest.raises(HTTPException):
        service.spend_coins(None, uuid4(), 10, None)

    # success
    progress_good = SimpleNamespace(coins=100)
    fake_db = FakeDB()
    monkeypatch.setattr(service, "get_or_create_progress", lambda db, uid: progress_good)
    res = service.spend_coins(fake_db, uuid4(), 10, None)
    assert res.coins == 90
    assert fake_db.committed


def test_upsert_concept_gap_create_and_update():
    user_id = uuid4()
    topic_id = uuid4()
    data = ConceptGapCreate(topic_id=topic_id, concept="Test", error_type=service.ErrorType.CONCEPTUAL, weakness_score=0.7)

    # create path: no existing gap
    db = FakeDB({"ConceptGap": None})
    gap = service.upsert_concept_gap(db, user_id, data)
    assert gap is not None

    # update path: existing gap
    existing = SimpleNamespace(user_id=user_id, topic_id=topic_id, concept="test", weakness_score=0.2, error_type=None, avg_response_time_ms=None)
    db2 = FakeDB({"ConceptGap": existing})
    data2 = ConceptGapCreate(topic_id=topic_id, concept="test", error_type=service.ErrorType.FACTUAL, weakness_score=0.9, avg_response_time_ms=123)
    gap2 = service.upsert_concept_gap(db2, user_id, data2)
    assert gap2.weakness_score == 0.9


def test_remove_concept_gap_not_found_and_found():
    user_id = uuid4()
    topic_id = uuid4()
    # not found
    db = FakeDB({"ConceptGap": None})
    res = service.remove_concept_gap(db, user_id, topic_id, "no")
    assert res is False

    # found
    gap = SimpleNamespace()
    db2 = FakeDB({"ConceptGap": gap})
    res2 = service.remove_concept_gap(db2, user_id, topic_id, "yes")
    assert res2 is True
    assert gap in db2.deleted or db2.deleted  # deletion attempted


def test_get_progress_by_period_no_topics():
    db = FakeDB({"Topic": []})
    res = service.get_progress_by_period(db, uuid4(), uuid4())
    assert res["topics_count"] == 0


def test_get_periods_mastery_empty():
    db = FakeDB({"HistoricalPeriod": []})
    res = service.get_periods_mastery(db, uuid4())
    assert res == []
