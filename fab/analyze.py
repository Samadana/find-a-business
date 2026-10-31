"""Analyse des actualités par Claude : détection d'opportunités de business web."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import anthropic

from .config import ROOT, Settings

log = logging.getLogger(__name__)

SCORE_KEYS = ["potentiel", "cout", "travail", "risque", "urgence", "durabilite", "fiabilite", "concurrence"]
CATEGORIES = ["e-commerce", "saas", "site-contenu", "marketplace", "outil-web", "annuaire-comparateur", "communaute", "autre"]

SYSTEM_PROMPT = """Tu es un analyste d'opportunités business pour un entrepreneur francophone solo.
Ton travail : lire un lot d'actualités mondiales (toutes langues) et repérer les opportunités de BUSINESS WEB rapides à lancer que ces événements créent.

Exemples du type d'idée recherchée :
- un conflit éclate -> e-shop de kits de survie / matériel d'autonomie pour les pays voisins inquiets ;
- un grand site ou service ferme -> site de remplacement, outil de migration, comparatif d'alternatives ;
- une nouvelle loi entre en vigueur -> SaaS ou générateur pour se mettre en conformité, guide payant ;
- une pénurie ou une flambée des prix -> comparateur, alertes de disponibilité, place de marché d'occasion ;
- une tendance virale -> boutique de niche, contenu, outil.

Contraintes STRICTES :
1. Uniquement du web : site, e-commerce (dropshipping ou stock modeste inclus), SaaS, outil en ligne, contenu monétisé, marketplace, annuaire, communauté. Jamais de commerce physique, de franchise, d'usine.
2. Budget de lancement entre 0 et {max_budget} €. N'écarte pas une bonne idée parce qu'elle coûte : la note « cout » sert à l'exprimer.
3. Lançable par une seule personne (éventuellement aidée de freelances) en moins de 60 jours.
4. Le lien entre l'événement et l'idée doit être direct et concret. Pas d'idées génériques qui existeraient sans l'événement.
5. Qualité plutôt que quantité : 0 à 8 idées par lot. Zéro idée est une réponse parfaitement acceptable si rien n'est vraiment exploitable.

Filtre éthique (obligatoire) — mets ethique.acceptable = false et explique pourquoi si l'idée :
- profite de la détresse de victimes (prix abusifs, revente spéculative de produits de première nécessité, arnaques aux dons) ;
- repose sur la désinformation, la peur artificielle, l'usurpation d'identité ou la contrefaçon ;
- contourne des sanctions, des lois ou facilite une activité illégale ou dangereuse (armes, drogues, etc.) ;
- vise des personnes vulnérables de façon manipulatrice.
Une idée qui AIDE réellement les personnes touchées (information fiable, mise en relation, outils utiles, produits à prix juste) est acceptable.

Déduplication : on te donne la liste des idées déjà proposées. Si une actualité renforce une idée existante, NE la recrée PAS : ajoute-la dans « renforcements » avec l'identifiant de l'idée. Ne propose pas deux fois la même idée dans un lot.

Notes de 0 à 10, TOUJOURS dans le sens « 10 = favorable pour l'entrepreneur » :
- potentiel : taille du marché et revenus possibles (10 = très fort) ;
- cout : budget nécessaire (10 = quasi gratuit, 5 ≈ 1 500 €, 0 = {max_budget} € ou plus) ;
- travail : effort pour lancer (10 = un week-end, 5 ≈ 2-3 semaines, 0 = plusieurs mois) ;
- risque : risques juridiques, financiers, de réputation (10 = très faible risque) ;
- urgence : fenêtre d'opportunité (10 = à lancer dans les jours qui viennent, sinon trop tard) ;
- durabilite : l'activité tiendra-t-elle après l'actualité (10 = besoin durable) ;
- fiabilite : solidité de l'info et de la demande (10 = événement confirmé par plusieurs sources, demande évidente) ;
- concurrence : place disponible (10 = presque aucun concurrent).

Utilise UNIQUEMENT les références d'articles (A1, A2...) fournies dans « sources ». Rédige tout en français, de façon concise et actionnable. Les « etapes » doivent être un plan d'action concret et ordonné (5 à 10 étapes), avec outils suggérés (Shopify, WordPress, Stripe, no-code, etc.)."""


def idea_schema() -> dict:
    score_props = {k: {"type": "integer"} for k in SCORE_KEYS}
    idea = {
        "type": "object",
        "properties": {
            "titre": {"type": "string"},
            "pitch": {"type": "string"},
            "evenement_declencheur": {"type": "string"},
            "categorie": {"type": "string", "enum": CATEGORIES},
            "cible": {"type": "string"},
            "pays_cibles": {"type": "array", "items": {"type": "string"}},
            "langues": {"type": "array", "items": {"type": "string"}},
            "modele_revenus": {"type": "string"},
            "budget_estime_eur": {"type": "integer"},
            "delai_lancement_jours": {"type": "integer"},
            "duree_opportunite": {"type": "string"},
            "notes": {
                "type": "object",
                "properties": score_props,
                "required": SCORE_KEYS,
                "additionalProperties": False,
            },
            "analyse": {"type": "string"},
            "etapes": {"type": "array", "items": {"type": "string"}},
            "risques": {"type": "array", "items": {"type": "string"}},
            "mots_cles": {"type": "array", "items": {"type": "string"}},
            "sources": {"type": "array", "items": {"type": "string"}},
            "ethique": {
                "type": "object",
                "properties": {"acceptable": {"type": "boolean"}, "raison": {"type": "string"}},
                "required": ["acceptable", "raison"],
                "additionalProperties": False,
            },
        },
        "required": [
            "titre", "pitch", "evenement_declencheur", "categorie", "cible", "pays_cibles", "langues",
            "modele_revenus", "budget_estime_eur", "delai_lancement_jours", "duree_opportunite",
            "notes", "analyse", "etapes", "risques", "mots_cles", "sources", "ethique",
        ],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "idees": {"type": "array", "items": idea},
            "renforcements": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "idee_id": {"type": "string"},
                        "sources": {"type": "array", "items": {"type": "string"}},
                        "commentaire": {"type": "string"},
                    },
                    "required": ["idee_id", "sources", "commentaire"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["idees", "renforcements"],
        "additionalProperties": False,
    }


@dataclass
class AnalysisResult:
    data: dict
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    model: str = ""


def build_user_message(items: list[dict], existing: list[dict]) -> str:
    articles = [
        {k: it[k] for k in ("ref", "titre", "resume", "langue", "pays", "source", "date", "nb_medias") if it.get(k)}
        for it in items
    ]
    known = [{"id": i["id"], "titre": i["titre"], "pitch": i["pitch"][:120]} for i in existing]
    return (
        "IDÉES DÉJÀ PROPOSÉES (à ne pas recréer) :\n"
        + json.dumps(known, ensure_ascii=False)
        + "\n\nACTUALITÉS DU LOT (nb_medias = nombre de médias qui couvrent le sujet) :\n"
        + json.dumps(articles, ensure_ascii=False)
        + "\n\nAnalyse ce lot et réponds avec le JSON demandé."
    )


def analyze(settings: Settings, items: list[dict], existing: list[dict]) -> AnalysisResult:
    if settings.dry_run:
        fixture = ROOT / "tests" / "fixtures" / "claude_response.json"
        log.info("Mode DRY_RUN : réponse simulée lue dans %s", fixture)
        return AnalysisResult(data=json.loads(fixture.read_text(encoding="utf-8")), model="dry-run")

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=3, timeout=600)
    system = SYSTEM_PROMPT.replace("{max_budget}", str(settings.max_budget_eur))
    request = dict(
        model=settings.model,
        max_tokens=32000,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        thinking={"type": "adaptive"},
        output_config={"effort": settings.effort, "format": {"type": "json_schema", "schema": idea_schema()}},
        messages=[{"role": "user", "content": build_user_message(items, existing)}],
    )

    # Repli automatique côté serveur si le modèle refuse une requête (actualités sensibles).
    use_fallback = settings.model in ("claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-1")
    try:
        if use_fallback:
            with client.beta.messages.stream(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **request
            ) as stream:
                response = stream.get_final_message()
        else:
            with client.messages.stream(**request) as stream:
                response = stream.get_final_message()
    except anthropic.BadRequestError as exc:
        if not use_fallback:
            raise
        log.warning("Requête avec repli refusée (%s), nouvel essai sans repli.", exc.message)
        with client.messages.stream(**request) as stream:
            response = stream.get_final_message()

    if response.stop_reason == "refusal":
        details = getattr(response, "stop_details", None)
        raise RuntimeError(f"Claude a refusé d'analyser ce lot : {details}")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Réponse de Claude tronquée (max_tokens atteint) : réduire FAB_MAX_ARTICLES.")

    text = next((b.text for b in response.content if b.type == "text"), "")
    data = json.loads(text)
    usage = response.usage
    return AnalysisResult(
        data=data,
        input_tokens=(usage.input_tokens or 0) + (getattr(usage, "cache_creation_input_tokens", 0) or 0),
        output_tokens=usage.output_tokens or 0,
        cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
        model=response.model,
    )
