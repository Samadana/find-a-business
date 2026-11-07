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


# --- Analyse en lots ---------------------------------------------------------------------------------------------

from fab.analyze import AnalysisResult, TriageResult  # noqa: E402
from fab.collect import Article  # noqa: E402
from fab.ideas import now_iso  # noqa: E402
from tests.test_ideas import idea  # noqa: E402

WORDS = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india"]


def batch_run(tmp_path, monkeypatch, behaviours, **kw):
    """Bilan réel (hors mode test) en 3 lots : `behaviours[i]` décide du sort du lot i ("ok" ou une exception)."""
    fixture = ROOT / "tests" / "fixtures" / "articles.json"
    articles = [Article(**{**a, "published": now_iso()}) for a in json.loads(fixture.read_text(encoding="utf-8"))]
    monkeypatch.setattr(fab_main, "collect_all", lambda sources, timeout: (articles, {}))
    monkeypatch.setattr(fab_main, "triage", lambda settings, items: TriageResult(refs=[c["ref"] for c in items]))
    monkeypatch.setattr(fab_main, "corroborate", lambda ideas, timeout: 0)
    reports, alerts, calls = [], [], []
    monkeypatch.setattr(fab_main.notify, "send_daily_report", lambda url, ideas, info, d, **k: reports.append(info) or 0)
    monkeypatch.setattr(fab_main.notify, "send_text", lambda url, text: alerts.append(text) or True)

    def fake_analyze(settings, items, existing, max_tokens=32000):
        n = len(calls)
        calls.append({"items": items, "existing": [i["titre"] for i in existing]})
        outcome = behaviours[n]
        if callable(outcome):
            outcome = outcome()
        if isinstance(outcome, Exception):
            raise outcome
        w = WORDS[n]
        data = {"idees": [idea(titre=f"Projet {w}", pitch=f"Pitch {w}", mots_cles=[w], sources=[items[0]["ref"]])]}
        return AnalysisResult(data=data, input_tokens=10_000, output_tokens=30_000, model="claude-opus-5-5")

    monkeypatch.setattr(fab_main, "analyze", fake_analyze)
    s = make_settings(tmp_path, **{"dry_run": False, "force": True, "analysis_batches": 3, "daily_cost_limit_usd": 0, **kw})
    info = fab_main.run(s)
    return s, info, calls, reports, alerts


def seen_ids(s):
    return set(json.loads(s.seen_path.read_text())) if s.seen_path.exists() else set()


def test_batches_all_ok_and_second_sees_first(tmp_path, monkeypatch):
    s, info, calls, reports, _ = batch_run(tmp_path, monkeypatch, ["ok", "ok", "ok"])
    assert info["statut"] == "ok" and len(info["lots"]) == 3 and info["idees_nouvelles"] == 3
    assert info["tokens_sortie"] == 90_000 and info["cout_usd"] == round(3 * (10_000 * 4 + 30_000 * 20) / 1e6, 4)
    assert calls[0]["existing"] == [] and calls[1]["existing"] == ["Projet alpha"]
    assert set(calls[2]["existing"]) == {"Projet alpha", "Projet bravo"}
    assert len(reports) == 1  # Discord une seule fois


def test_failed_batch_keeps_other_ideas_and_frees_its_articles(tmp_path, monkeypatch):
    s, info, calls, reports, alerts = batch_run(tmp_path, monkeypatch, ["ok", RuntimeError("Réponse tronquée"), "ok"])
    assert info["statut"] == "partiel : 1 lot sur 3 en échec ou non analysé"
    assert info["idees_nouvelles"] == 2 and info["lots"][1]["statut"].startswith("échec")
    failed = {aid for it in calls[1]["items"] for aid in it["ids"]}
    done = {aid for c in (calls[0], calls[2]) for it in c["items"] for aid in it["ids"]}
    seen = seen_ids(s)
    assert failed and not (failed & seen) and done <= seen  # exclus des deux boucles qui marquent `seen`
    assert info["sujets_analyses"] == len(calls[0]["items"]) + len(calls[2]["items"])
    assert not alerts and len(reports) == 1


def test_all_batches_failed_behaves_as_before(tmp_path, monkeypatch):
    s, info, _, reports, _ = batch_run(tmp_path, monkeypatch, [RuntimeError("panne")] * 3)
    assert info["statut"] == "erreur : panne" and not reports
    assert not s.seen_path.exists() and json.loads(s.ideas_path.read_text()) == []


def test_credit_exhausted_stops_remaining_batches(tmp_path, monkeypatch):
    s, info, calls, _, alerts = batch_run(tmp_path, monkeypatch, ["ok", RuntimeError("Your credit balance is too low"), "ok"])
    assert len(calls) == 2 and info["statut"].startswith("partiel : 2 lots sur 3")
    assert info["lots"][2]["statut"] == "non analysé (arrêt)" and "crédit" in alerts[0]
    # Crédit épuisé dès le premier lot : comme avant (erreur, `seen` non sauvegardé).
    s2, info2, calls2, _, _ = batch_run(tmp_path / "b", monkeypatch, [RuntimeError("billing error")] * 3)
    assert len(calls2) == 1 and info2["statut"].startswith("erreur") and not s2.seen_path.exists()


def test_cost_limit_reached_between_batches(tmp_path, monkeypatch):
    # Un lot coûte 0,64 $ ; coût maximal estimé d'un lot ≈ 0,65 $ : le 2e dépasserait 1 $.
    s, info, calls, _, _ = batch_run(tmp_path, monkeypatch, ["ok", "ok", "ok"], daily_cost_limit_usd=1.0)
    assert len(calls) == 1 and [lot["statut"] for lot in info["lots"]][1:] == ["non analysé (plafond)"] * 2
    assert info["statut"].startswith("partiel : 2 lots sur 3")


def test_batch_deadline(tmp_path, monkeypatch):
    now = [0.0]
    monkeypatch.setattr(fab_main, "clock", lambda: now[0])

    def slow():
        now[0] += 26 * 60  # le premier lot dure 26 min
        return "ok"
    s, info, calls, _, _ = batch_run(tmp_path, monkeypatch, [slow, "ok", "ok"])
    assert len(calls) == 1 and info["lots"][1]["statut"] == "non analysé (échéance)"


def test_dry_run_uses_a_single_batch(tmp_path):
    s = make_settings(tmp_path, analysis_batches=3)
    info = fab_main.run(s)
    assert info["statut"] == "ok" and len(info["lots"]) == 1 and info["lots"][0]["statut"] == "ok"
