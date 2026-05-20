from uuid import uuid4
from types import SimpleNamespace
from datetime import datetime, timezone

from app.modules.learning import service


def test_calculate_level():
    assert service._calculate_level(0) == 1
    assert service._calculate_level(100) == 2
    assert service._calculate_level(450) == 5


def test_classify_error_type():
    r1 = service._classify_error_type(100)
    r2 = service._classify_error_type(4000)
    assert getattr(r1, "name", str(r1)).upper().startswith("CONCEPT")
    assert getattr(r2, "name", str(r2)).upper().startswith("FACT") or getattr(r2, "name", str(r2)).upper().startswith("CONTEXT")


def test_compute_session_outcome_basic():
    data = SimpleNamespace(correct_answers=3, wrong_answers=1, completed=True)
    xp, coins, lives = service._compute_session_outcome(data, available_lives=5)
    assert xp <= service.MAX_XP_PER_SESSION
    assert coins <= service.MAX_COINS_PER_SESSION
    assert lives == 1
