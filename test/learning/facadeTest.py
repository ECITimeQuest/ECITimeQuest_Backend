from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.learning.facade import LearningFacade


def test_get_user_learning_context_success(monkeypatch):
    fake_db = SimpleNamespace()
    expected = {"foo": "bar"}

    def fake_get_learning_context_for_ai(db, user_id, topic_id):
        assert db is fake_db
        return expected

    monkeypatch.setattr("app.modules.learning.facade.get_learning_context_for_ai", fake_get_learning_context_for_ai)

    facade = LearningFacade(fake_db)
    res = facade.get_user_learning_context(str(uuid4()), str(uuid4()))
    assert res == expected


def test_get_user_learning_context_exception_returns_empty(monkeypatch):
    fake_db = SimpleNamespace()

    def fake_raise(db, user_id, topic_id):
        raise Exception("boom")

    monkeypatch.setattr("app.modules.learning.facade.get_learning_context_for_ai", fake_raise)

    facade = LearningFacade(fake_db)
    res = facade.get_user_learning_context(str(uuid4()), str(uuid4()))
    assert res == {}
