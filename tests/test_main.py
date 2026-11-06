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
    monkeypatch.setattr(fab_main.notify, "send_ideas", lambda url, ideas, d, test=False, **kw: sent.extend(ideas) or len(ideas))
    s = make_settings(tmp_path, min_score_notify=6.8, discord_webhook_url="https://discord/x")
    fab_main.run(s)
    assert [i["note_globale"] >= 6.8 for i in sent] == [True] * len(sent) and len(sent) == 1


def test_triage_failure_falls_back_to_heuristic(tmp_path, monkeypatch):
    def boom(settings, items):
        raise RuntimeError("panne")
    monkeypatch.setattr(fab_main, "triage", boom)
    info = fab_main.run(make_settings(tmp_path))
    assert info["statut"] == "ok" and info["sujets_analyses"] == info["sujets_candidats"]


def test_daily_guard(tmp_path, monkeypatch):
    from datetime import datetime as real_dt
    from zoneinfo import ZoneInfo

    class FakeDT(real_dt):
        hour_value = 8

        @classmethod
        def now(cls, tz=None):
            return real_dt(2026, 11, 2, cls.hour_value, 5, tzinfo=ZoneInfo("Europe/Paris")).astimezone(tz)

    monkeypatch.setattr(fab_main, "datetime", FakeDT)
    s = make_settings(tmp_path, dry_run=False, force=False)
    assert fab_main.run(s)["statut"] == "ignoré : trop tôt"
    assert not s.stats_path.exists()
    # Bilan déjà fait aujourd'hui -> rien
    s.stats_path.write_text(json.dumps({"historique": [], "dernier_bilan": "2026-11-02"}))
    FakeDT.hour_value = 9
    assert fab_main.run(s)["statut"] == "ignoré : bilan déjà fait"


def test_report_sent_even_without_ideas(tmp_path, monkeypatch):
    texts = []
    monkeypatch.setattr(fab_main.notify, "_post", lambda url, payload, att=None: texts.append((payload["content"], att)) or True)
    s = make_settings(tmp_path, discord_webhook_url="https://discord/x", min_new_articles=1000)
    info = fab_main.run(s)
    assert info["statut"] == "rien de neuf" and "Bilan du jour" in texts[0][0]
    assert texts[0][1] is None  # plus de fichier HTML joint par défaut
    assert json.loads(s.stats_path.read_text())["dernier_bilan"]


def test_rescore_runs_even_when_nothing_new(tmp_path):
    s = make_settings(tmp_path)
    fab_main.run(s)
    ideas = json.loads(s.ideas_path.read_text())
    ideas[0]["note_globale"] = 0.1  # note calculée avec une ancienne formule
    s.ideas_path.write_text(json.dumps(ideas))
    info = fab_main.run(s)
    assert info["statut"] == "rien de neuf" and info["idees_renotees"] == 1
    assert all(i["note_globale"] > 0.1 for i in json.loads(s.ideas_path.read_text()))
