import pytest

from types import SimpleNamespace


def test_verify_firebase_token_success(monkeypatch):
    import app.core.firebase as fb

    monkeypatch.setattr(fb.auth, "verify_id_token", lambda token: {"uid": "user1"})
    res = fb.verify_firebase_token("token")
    assert isinstance(res, dict)
    assert res["uid"] == "user1"


def test_verify_firebase_token_failure(monkeypatch):
    import app.core.firebase as fb

    def raise_err(token):
        raise Exception("invalid")

    monkeypatch.setattr(fb.auth, "verify_id_token", raise_err)
    res = fb.verify_firebase_token("bad")
    assert res is None
