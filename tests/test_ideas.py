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


def test_forbidden_match_ignores_protective_wording():
    from fab.ideas import forbidden_match
    assert forbidden_match("guide pour retirer ses fonds, anti-arnaques au remboursement") is None
    assert forbidden_match("aider les victimes à éviter les arnaques") is None
    assert forbidden_match("outil pour détecter la contrefaçon") is None
    assert forbidden_match("vendre des produits de contrefaçon") == "contrefaçon"
    assert forbidden_match("une arnaque au faux remboursement") == "arnaque"


def test_resolve_sources_adds_other_outlets():
    from fab.ideas import resolve_sources
    items = {"A1": {"titre": "t", "url": "u1", "source": "BBC", "langue": "en", "date": "d",
                    "autres_sources": [{"titre": "t2", "url": "u2", "source": "Reuters", "langue": "en", "date": "d"}]}}
    assert [s["url"] for s in resolve_sources(["A1"], items)] == ["u1", "u2"]


def test_strip_dev_costs_in_english():
    from fab.ideas import strip_dev_costs
    idea = {"budget_estime_eur": 2100, "budget_detail": [
        "Domain and hosting: €80", "Freelance developer for the API connector: €1,500", "Google Ads: €520.50"]}
    assert strip_dev_costs(idea) == 1500
    assert idea["budget_estime_eur"] == 600
    assert idea["budget_detail"] == ["Domain and hosting: €80", "Google Ads: €520.50"]


def test_forbidden_match_in_english():
    from fab.ideas import forbidden_match
    assert forbidden_match("a tool to help victims avoid scams") is None
    assert forbidden_match("anti-scam checklist for refunds") is None
    assert forbidden_match("detect counterfeit sneakers") is None
    assert forbidden_match("sell counterfeit sneakers") == "counterfeit"
    assert forbidden_match("help companies evade sanctions") == "evade sanctions"


def test_new_ideas_are_marked_as_written_in_english():
    from fab.analyze import SYSTEM_PROMPT
    assert "en ANGLAIS américain" in SYSTEM_PROMPT


def test_no_budget_cap_by_default_and_online_flag_is_kept():
    ideas = []
    shop = idea(titre="Dépôt-vente de groupes électrogènes à Rafah", categorie="commerce-physique",
                budget_estime_eur=45000, realisable_en_ligne=False, mots_cles=["generateurs"])
    new, rej, _ = process_analysis({"idees": [shop, idea()]}, ITEMS, ideas)
    assert not rej
    assert new[0]["budget_estime_eur"] == 45000 and new[0]["realisable_en_ligne"] is False
    assert new[1]["realisable_en_ligne"] is True  # absent = en ligne (anciennes réponses)
    # Un plafond explicite reste possible.
    _, rej, _ = process_analysis({"idees": [idea(titre="Autre boutique", mots_cles=["autre"], budget_estime_eur=9000)]}, ITEMS, [], 5000)
    assert rej and "9000" in rej[0]["raison"]


def test_ai_coding_subscription_stays_in_budget_but_freelancers_do_not():
    from fab.ideas import strip_dev_costs
    i = idea(budget_estime_eur=1260, budget_detail=[
        "AI coding assistant subscription (2 months): €200",
        "Abonnement à l'IA de développement (1 mois) : 20 €",
        "Freelance developer to integrate the AI API: €1,000",
        "Domain: €40",
    ])
    assert strip_dev_costs(i) == 1000
    assert i["budget_estime_eur"] == 260
    assert len(i["budget_detail"]) == 3


def test_prompt_and_schema_cover_every_kind_of_business():
    from fab.analyze import CATEGORIES, SYSTEM_PROMPT, TRIAGE_PROMPT, idea_schema
    props = idea_schema()["properties"]["idees"]["items"]
    assert props["properties"]["realisable_en_ligne"] == {"type": "boolean"}
    assert "realisable_en_ligne" in props["required"]
    assert {"commerce-physique", "service-local", "restauration"} <= set(CATEGORIES)
    assert "{max_budget}" not in SYSTEM_PROMPT
    assert "IA de développement" in SYSTEM_PROMPT and "hors ligne" in TRIAGE_PROMPT


def test_weights_sum_to_one():
    from fab.ideas import TIMING_WEIGHT, WEIGHTS
    assert "urgence" not in WEIGHTS and "durabilite" not in WEIGHTS
    assert abs(sum(WEIGHTS.values()) + TIMING_WEIGHT - 1) < 1e-9


def test_global_score_combines_urgency_and_durability_into_timing():
    perfect = {k: 10 for k in BASE["notes"]}
    assert global_score(perfect) == 10.0
    assert global_score({k: 0 for k in BASE["notes"]}) == 0.0
    # 0,24×8 + 0,14×9 + 0,11×9 + 0,11×8 + 0,10×6 + 0,10×7 + 0,20×(0,7×10 + 0,3×3) = 7.93
    assert global_score(BASE["notes"]) == 7.9
    # Urgent OU durable : même note, l'une ne pénalise pas l'autre.
    urgent = {**BASE["notes"], "urgence": 10, "durabilite": 2}
    durable = {**BASE["notes"], "urgence": 2, "durabilite": 10}
    assert global_score(urgent) == global_score(durable)
    # Urgent ET durable reste la meilleure combinaison.
    assert global_score({**BASE["notes"], "urgence": 10, "durabilite": 10}) > global_score(urgent)


def _old_global_score(notes):
    old = {"potentiel": 0.22, "fiabilite": 0.16, "durabilite": 0.14, "risque": 0.12, "cout": 0.10,
           "travail": 0.10, "concurrence": 0.10, "urgence": 0.06}
    return round(sum(notes[k] * w for k, w in old.items()), 1)


def test_new_formula_does_not_lower_urgent_or_durable_ideas():
    for u, d in [(10, 10), (10, 3), (3, 10), (9, 8), (8, 9)]:
        notes = {**BASE["notes"], "urgence": u, "durabilite": d}
        assert global_score(notes) >= _old_global_score(notes), (u, d)


def test_new_idea_has_last_signal_date_and_reinforce_updates_it():
    from fab.ideas import reinforce
    ideas = []
    process_analysis({"idees": [idea()]}, ITEMS, ideas)
    assert ideas[0]["dernier_signal_le"] == ideas[0]["cree_le"]
    ideas[0]["dernier_signal_le"] = "2020-01-01T00:00:00+00:00"
    reinforce(ideas[0], [], "re")
    assert ideas[0]["dernier_signal_le"] == ideas[0]["mis_a_jour_le"] != "2020-01-01T00:00:00+00:00"


def test_archive_old_uses_last_signal_date():
    from fab.ideas import now_iso
    recent = now_iso()
    # Renotée récemment mais sans nouvelle actualité depuis longtemps -> archivée.
    stale = {"statut": "active", "mis_a_jour_le": recent, "dernier_signal_le": "2020-01-01T00:00:00+00:00"}
    # Ancien champ seul (idées d'avant) -> repli sur mis_a_jour_le.
    fresh = {"statut": "active", "mis_a_jour_le": recent}
    ideas = [stale, fresh]
    assert archive_old(ideas, 30) == 1
    assert stale["statut"] == "archivee" and fresh["statut"] == "active"


def test_rescore_updates_only_changed_active_ideas():
    from fab.ideas import rescore
    old_date = "2026-10-01T07:30:00+00:00"
    notes = dict(BASE["notes"])
    good = global_score(notes, 2)
    unchanged = {"statut": "active", "notes": notes, "signaux": 2, "note_globale": good, "mis_a_jour_le": old_date}
    changed = {"statut": "active", "notes": notes, "signaux": 1, "note_globale": 5.0, "mis_a_jour_le": old_date}
    already = {"statut": "active", "notes": notes, "signaux": 1, "note_globale": 5.0, "mis_a_jour_le": old_date,
               "dernier_signal_le": "2026-09-15T07:30:00+00:00"}
    archived = {"statut": "archivee", "notes": notes, "signaux": 1, "note_globale": 5.0, "mis_a_jour_le": old_date}
    before_archived = copy.deepcopy(archived)

    assert rescore([unchanged, changed, already, archived]) == 2
    assert unchanged["mis_a_jour_le"] == old_date and "dernier_signal_le" not in unchanged
    assert changed["note_globale"] == global_score(notes, 1)
    assert changed["dernier_signal_le"] == old_date and changed["mis_a_jour_le"] > old_date
    assert already["dernier_signal_le"] == "2026-09-15T07:30:00+00:00" and already["mis_a_jour_le"] > old_date
    assert archived == before_archived
    # Un second passage ne change plus rien.
    assert rescore([unchanged, changed, already, archived]) == 0


def test_rescored_idea_is_still_archived_on_time():
    from fab.ideas import rescore
    old = {"statut": "active", "notes": dict(BASE["notes"]), "signaux": 1, "note_globale": 1.0,
           "mis_a_jour_le": "2020-01-01T00:00:00+00:00"}
    assert rescore([old]) == 1
    assert archive_old([old], 30) == 1


def test_prompt_has_numeric_anchors_for_every_score():
    from fab.analyze import SYSTEM_PROMPT
    for anchor in ("20 000 €", "géants installés", "mise perdue < 500 €", "besoin permanent", "fenêtre de quelques jours",
                   "fait officiel", "ne peut pas dépasser 6 en fiabilité", "utilise toute l'échelle"):
        assert anchor in SYSTEM_PROMPT, anchor
