import copy

from fab.ideas import archive_old, ethics_check, global_score, process_analysis

ITEMS = [{"ref": "A1", "titre": "PixNest ferme", "url": "https://x/1", "source": "S", "langue": "fr", "date": "d", "ids": ["1"]},
         {"ref": "A2", "titre": "Loi", "url": "https://x/2", "source": "S", "langue": "fr", "date": "d", "ids": ["2"]}]

BASE = {
    "titre": "Outil d'export PixNest", "pitch": "Exporter ses photos.", "evenement_declencheur": "Fermeture",
    "categorie": "outil-web", "cible": "Utilisateurs", "pays_cibles": ["Monde"], "langues": ["fr"],
    "modele_revenus": "9 €", "budget_estime_eur": 500, "delai_lancement_jours": 7, "duree_opportunite": "2 mois",
    "notes": {"potentiel": 8, "cout": 9, "travail": 7, "risque": 8, "urgence": 10, "durabilite": 3, "fiabilite": 9, "concurrence": 6},
    "analyse": "ok", "etapes": ["a"], "risques": ["b"], "mots_cles": ["pixnest", "export"], "sources": ["A1"],
    "ethique": {"acceptable": True, "raison": "utile"},
}


def idea(**kw):
    d = copy.deepcopy(BASE)
    d.update(kw)
    return d


def test_global_score_and_bonus():
    n = BASE["notes"]
    assert 0 <= global_score(n) <= 10
    assert global_score(n, 4) == round(global_score(n) + 0.3, 1)


def test_new_idea_is_added_with_metadata():
    ideas = []
    new, rej, reinf = process_analysis({"idees": [idea()], "renforcements": []}, ITEMS, ideas, 5000)
    assert len(new) == 1 and not rej and reinf == 0
    i = ideas[0]
    assert i["id"].startswith("idee-") and i["sources"][0]["url"] == "https://x/1" and i["signaux"] == 1


def test_ethics_and_budget_and_sources_filters():
    data = {"idees": [
        idea(titre="A", ethique={"acceptable": False, "raison": "exploite les victimes"}),
        idea(titre="B", pitch="Vendre des bâches à prix abusifs", mots_cles=["b"]),
        idea(titre="C", budget_estime_eur=9000, mots_cles=["c"]),
        idea(titre="D", sources=["A99"], mots_cles=["d"]),
    ], "renforcements": []}
    ideas = []
    new, rej, _ = process_analysis(data, ITEMS, ideas, 5000)
    assert not new and len(rej) == 4
    assert "victimes" in rej[0]["raison"] and "prix abusif" in rej[1]["raison"]
    assert "Budget" in rej[2]["raison"] and "source" in rej[3]["raison"]


def test_scores_are_clamped():
    ideas = []
    new, _, _ = process_analysis({"idees": [idea(notes={**BASE["notes"], "cout": 42, "risque": -3})]}, ITEMS, ideas, 5000)
    assert new[0]["notes"]["cout"] == 10 and new[0]["notes"]["risque"] == 0


def test_duplicates_across_runs_become_reinforcements():
    ideas = []
    process_analysis({"idees": [idea()]}, ITEMS, ideas, 5000)
    first_id = ideas[0]["id"]
    # même idée reformulée, autre source -> fusion automatique
    new, _, reinf = process_analysis({"idees": [idea(titre="Outil d'export pour PixNest", sources=["A2"])]}, ITEMS, ideas, 5000)
    assert not new and reinf == 1 and len(ideas) == 1
    assert ideas[0]["signaux"] == 2 and len(ideas[0]["sources"]) == 2
    # renforcement explicite proposé par Claude
    process_analysis({"idees": [], "renforcements": [{"idee_id": first_id, "sources": ["A1"], "commentaire": "re"}]}, ITEMS, ideas, 5000)
    assert ideas[0]["signaux"] == 3 and len(ideas[0]["sources"]) == 2


def test_duplicates_within_same_batch():
    ideas = []
    new, _, reinf = process_analysis({"idees": [idea(), idea(titre="Outil d'export PixNest !")]}, ITEMS, ideas, 5000)
    assert len(new) == 1 and reinf == 1


def test_ethics_check_accepts_helpful_idea():
    ok, _ = ethics_check(idea(titre="Carte des points d'eau gratuits pour sinistrés"))
    assert ok


def test_archive_old():
    ideas = [{"statut": "active", "mis_a_jour_le": "2020-01-01T00:00:00+00:00"}]
    assert archive_old(ideas, 30) == 1 and ideas[0]["statut"] == "archivee"


def test_strip_dev_costs():
    from fab.ideas import strip_dev_costs
    idea = {"budget_estime_eur": 1180, "budget_detail": [
        "Nom de domaine + hébergement : 80 €",
        "Développement freelance du connecteur : 400 €",
        "Agence web pour l'intégration : 1 000 €" if False else "Publicité Google Ads : 700 €",
    ]}
    assert strip_dev_costs(idea) == 400
    assert idea["budget_estime_eur"] == 780
    assert idea["budget_detail"] == ["Nom de domaine + hébergement : 80 €", "Publicité Google Ads : 700 €"]


def test_strip_dev_costs_keeps_other_lines():
    from fab.ideas import strip_dev_costs
    idea = {"budget_estime_eur": 200, "budget_detail": ["API OpenStreetMap : 0 €", "Logo sur Fiverr : 50 €"]}
    assert strip_dev_costs(idea) == 0 and idea["budget_estime_eur"] == 200


def test_strip_dev_costs_keeps_non_dev_freelances():
    from fab.ideas import strip_dev_costs
    idea = {"budget_estime_eur": 700, "budget_detail": [
        "Relecture par un avocat freelance : 400 €", "Développeur freelance (graphiques, alertes) : 300 €"]}
    assert strip_dev_costs(idea) == 300
    assert idea["budget_detail"] == ["Relecture par un avocat freelance : 400 €"] and idea["budget_estime_eur"] == 400
