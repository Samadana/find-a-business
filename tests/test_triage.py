import json
from types import SimpleNamespace

from fab import analyze as an
from fab.config import Settings


class FakeStream:
    def __init__(self, text):
        self.msg = SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)],
                                   usage=SimpleNamespace(input_tokens=1000, output_tokens=50))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self.msg


def test_triage_filters_unknown_refs_and_duplicates(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, **kw):
            self.messages = SimpleNamespace(stream=self.stream)

        def stream(self, **kw):
            captured.update(kw)
            return FakeStream(json.dumps({"retenus": ["A2", "A2", "A999", "A1"]}))

    monkeypatch.setattr(an.anthropic, "Anthropic", FakeClient)
    s = Settings()
    s.dry_run = False
    s.max_articles_per_run = 1
    items = [{"ref": "A1", "titre": "x", "nb_medias": 3}, {"ref": "A2", "titre": "y", "resume": "z"}]
    res = an.triage(s, items)
    assert res.refs == ["A2", "A1"] and res.input_tokens == 1000
    assert captured["model"] == "claude-haiku-5-5"
    assert "A1 | ? | x | 3 médias" in captured["messages"][0]["content"]


def test_triage_skipped_when_few_items():
    s = Settings()
    s.dry_run = False
    s.max_articles_per_run = 60
    assert an.triage(s, [{"ref": "A1", "titre": "x"}]).refs == ["A1"]
