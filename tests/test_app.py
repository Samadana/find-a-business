import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import serveur  # noqa: E402


def test_validate_settings_ok():
    out = serveur.validate_settings(
        {"FAB_MIN_SCORE_NOTIFY": "7.0", "FAB_MODEL": "claude-sonnet-5-5", "FAB_DAILY_COST_LIMIT_USD": 1.5}
    )
    assert out == {"FAB_MIN_SCORE_NOTIFY": "7", "FAB_MODEL": "claude-sonnet-5-5", "FAB_DAILY_COST_LIMIT_USD": "1.5"}


@pytest.mark.parametrize("values", [
    {"FAB_MIN_SCORE_NOTIFY": "11"},
    {"FAB_MIN_SCORE_NOTIFY": "abc"},
    {"FAB_MODEL": "gpt-4"},
    {"FAB_DAILY_COST_LIMIT_USD": "-1"},
])
def test_validate_settings_refuse(values):
    with pytest.raises(ValueError):
        serveur.validate_settings(values)


def test_update_json_retries_on_conflict(monkeypatch):
    gh = serveur.GitHub("t", "o/r")
    calls = {"put": 0}

    def fake(method, path, body=None, raw=False):
        if method == "GET":
            raise serveur.GitHubError(404, "absent")
        calls["put"] += 1
        if calls["put"] == 1:
            raise serveur.GitHubError(409, "conflit")
        return {}

    monkeypatch.setattr(gh, "request", fake)
    monkeypatch.setattr(serveur.time, "sleep", lambda s: None)
    result = gh.update_json("data/suivi.json", lambda cur: {**cur, "a": 1}, "msg")
    assert result == {"a": 1} and calls["put"] == 2
