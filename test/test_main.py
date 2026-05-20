from contextlib import contextmanager
from types import SimpleNamespace
from fastapi.testclient import TestClient


def test_root():
    from app.main import app
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "mensaje" in resp.json()


def test_health(monkeypatch):
    # create a fake engine.connect context manager
    class FakeConn:
        def execute(self, *args, **kwargs):
            return None

    @contextmanager
    def fake_connect():
        yield FakeConn()

    import app.main as m
    monkeypatch.setattr(m, "engine", SimpleNamespace(connect=fake_connect))

    from app.main import app
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json().get("estado") == "ok"
