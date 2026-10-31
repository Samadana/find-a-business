from fab import notify
from tests.test_ideas import BASE, ITEMS, idea
from fab.ideas import process_analysis


TITLES = ["Comparateur de prix de l'huile", "Boutique de kits d'urgence", "SaaS de facturation", "Annuaire de réparateurs vélo",
          "Plateforme de covoiturage scolaire", "Guide des aides énergie", "Marketplace de pièces détachées", "Outil de veille réglementaire",
          "Site d'alertes de stock", "Communauté de télétravailleurs", "Générateur de contrats", "Traducteur de menus"]


def make_ideas(n):
    ideas = []
    process_analysis({"idees": [idea(titre=t, mots_cles=[t], pitch="p" * 1400) for t in TITLES[:n]]}, ITEMS, ideas, 5000)
    return ideas


def test_embed_contains_scores_and_link():
    i = make_ideas(1)[0]
    e = notify.build_embed(i, "https://me.github.io/fab/")
    assert e["url"].endswith("#" + i["id"])
    assert any(f["name"].startswith("Notes") for f in e["fields"])
    assert notify.embed_size(e) < 6000


def test_grouping_respects_discord_limits():
    embeds = [notify.build_embed(i, "") for i in make_ideas(12)]
    groups = notify.group_embeds(embeds)
    assert sum(len(g) for g in groups) == 12
    for g in groups:
        assert len(g) <= 10 and sum(notify.embed_size(e) for e in g) <= 5500


def test_send_ideas_posts_and_marks(monkeypatch):
    calls = []
    monkeypatch.setattr(notify, "_post", lambda url, payload: calls.append(payload) or True)
    monkeypatch.setattr(notify.time, "sleep", lambda s: None)
    ideas = make_ideas(4)
    assert notify.send_ideas("https://discord/webhook", ideas, "https://d/") == 4
    assert all(i["notifiee"] for i in ideas)
    assert "4 nouvelles opportunités" in calls[0]["content"]


def test_no_webhook_no_send():
    assert notify.send_ideas("", make_ideas(1), "") == 0
