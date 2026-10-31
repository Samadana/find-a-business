import json
import shutil

from fab import main as fab_main
from fab.config import ROOT, Settings


def make_settings(tmp_path, **kw):
    s = Settings()
    s.dry_run = True
    s.discord_webhook_url = ""
    s.seen_path = tmp_path / "seen.json"
    s.ideas_path = tmp_path / "ideas.json"
    s.rejected_path = tmp_path / "rejected.json"
    s.stats_path = tmp_path / "stats.json"
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def test_dry_run_end_to_end_then_nothing_new(tmp_path):
    s = make_settings(tmp_path)
    info = fab_main.run(s)
    assert info["statut"] == "ok" and info["idees_nouvelles"] == 2 and info["idees_ecartees"] == 1
    ideas = json.loads(s.ideas_path.read_text())
    assert len(ideas) == 2 and ideas[0]["note_globale"] >= ideas[1]["note_globale"]
    # Deuxième passage : les mêmes articles sont déjà vus -> pas d'appel à Claude
    info2 = fab_main.run(s)
    assert info2["statut"] == "rien de neuf"
    assert len(json.loads(s.stats_path.read_text())["historique"]) == 2


def test_daily_cost_limit_blocks_analysis(tmp_path):
    s = make_settings(tmp_path, daily_cost_limit_usd=1.0)
    from fab.ideas import now_iso
    s.stats_path.write_text(json.dumps({"historique": [{"date": now_iso(), "cout_usd": 2.0}]}))
    info = fab_main.run(s)
    assert info["statut"] == "plafond quotidien atteint"
    assert not s.seen_path.exists() or json.loads(s.seen_path.read_text()) == {}


def test_notifies_only_above_threshold(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(fab_main.notify, "send_ideas", lambda url, ideas, d, test=False: sent.extend(ideas) or len(ideas))
    s = make_settings(tmp_path, min_score_notify=6.8)
    fab_main.run(s)
    assert [i["note_globale"] >= 6.8 for i in sent] == [True] * len(sent) and len(sent) == 1
