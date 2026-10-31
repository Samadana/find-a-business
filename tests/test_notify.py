from fab import notify
from fab.ideas import process_analysis
from tests.test_ideas import ITEMS, idea

TITLES = ["Comparateur de prix de l'huile", "Boutique de kits d'urgence", "SaaS de facturation", "Annuaire de réparateurs vélo",
          "Plateforme de covoiturage scolaire", "Guide des aides énergie", "Marketplace de pièces détachées", "Outil de veille réglementaire",
          "Site d'alertes de stock", "Communauté de télétravailleurs", "Générateur de contrats", "Traducteur de menus"]


def make_ideas(n, long=False):
    ideas = []
    extra = {}
    if long:
        big = "x" * 5000
        extra = {"description_detaillee": big, "contexte_declencheur": big, "pourquoi_maintenant": big,
                 "notes_explications": {k: big for k in notify.LABELS}, "budget_detail": [big] * 3,
                 "concurrents": [big] * 3, "etapes": [big] * 12, "risques": [big] * 5, "analyse": big,
                 "cible": big, "modele_revenus": big}
    process_analysis({"idees": [idea(titre=t, mots_cles=[t], **extra) for t in TITLES[:n]]}, ITEMS, ideas, 5000)
    return ideas


def test_idea_embeds_are_detailed_and_within_discord_limits():
    i = make_ideas(1, long=True)[0]
    embeds = notify.build_idea_embeds(i, "https://me.github.io/fab/")
    assert [e["title"][0] for e in embeds] == ["💡", "📰", "📊", "🛠"]
    assert embeds[0]["url"].endswith("#" + i["id"])
    assert len(embeds[2]["fields"]) == 8  # une explication par note
    for e in embeds:
        assert notify.embed_size(e) <= 6000
        assert len(e.get("description", "")) <= 4096
        assert all(len(f["value"]) <= 1024 and len(f["name"]) <= 256 for f in e["fields"])
    for g in notify.group_embeds(embeds):
        assert sum(notify.embed_size(e) for e in g) <= 6000


def test_score_explanations_shown():
    i = make_ideas(1)[0]
    i["notes_explications"] = {k: f"explication {k}" for k in notify.LABELS}
    scores = notify.build_idea_embeds(i)[2]
    assert "explication cout" in scores["fields"][1]["value"]


def test_send_ideas_posts_header_then_each_idea(monkeypatch):
    calls = []
    monkeypatch.setattr(notify, "_post", lambda url, payload, att=None: calls.append(payload) or True)
    monkeypatch.setattr(notify.time, "sleep", lambda s: None)
    ideas = make_ideas(3)
    assert notify.send_ideas("https://discord/webhook", ideas, "") == 3
    assert all(i["notifiee"] for i in ideas)
    assert "3 nouvelles opportunités" in calls[0]["content"]
    assert sum(1 for c in calls if c.get("content", "").startswith("**Idée")) == 3


def test_no_webhook_no_send():
    assert notify.send_ideas("", make_ideas(1), "") == 0


def test_report_without_ideas_has_no_attachment_by_default(monkeypatch):
    calls = []
    monkeypatch.setattr(notify, "_post", lambda url, payload, att=None: calls.append((payload, att)) or True)
    notify.send_daily_report("https://discord/x", [], {"sujets_analyses": 3}, "")
    assert "Bilan du jour" in calls[0][0]["content"] and calls[0][1] is None


def test_daily_report_lists_ideas_below_threshold(monkeypatch):
    from fab import notify
    posts = []
    monkeypatch.setattr(notify, "_post", lambda url, payload, attachment=None: posts.append(payload) or True)
    below = [{"titre": "Idée moyenne", "note_globale": 6.1}, {"titre": "Idée faible", "note_globale": 5.7}]
    notify.send_daily_report("https://x", [], {"idees_nouvelles": 2}, "", below=below, threshold=6.5)
    text = posts[0]["content"]
    assert "aucune idée n'atteint ta note minimale (6.5/10)" in text
    assert "6.1/10 · Idée moyenne" in text and "5.7/10 · Idée faible" in text
