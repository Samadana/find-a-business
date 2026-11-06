"""Analyse des actualités par Claude : détection d'opportunités de business (en ligne ou non)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import anthropic

from .config import ROOT, Settings

log = logging.getLogger(__name__)

SCORE_KEYS = ["potentiel", "cout", "travail", "risque", "urgence", "durabilite", "fiabilite", "concurrence"]
# Les catégories en ligne d'abord, puis celles qui demandent une présence physique.
CATEGORIES = [
    "e-commerce", "saas", "site-contenu", "marketplace", "outil-web", "annuaire-comparateur", "communaute",
    "commerce-physique", "service-local", "import-negoce", "production-artisanat", "restauration", "evenementiel", "autre",
]

SYSTEM_PROMPT = """Tu es un analyste d'opportunités business pour des entrepreneurs qui se lancent seuls.
Ton travail : lire un lot d'actualités mondiales (toutes langues) et repérer les opportunités de BUSINESS rapides à lancer que ces événements créent,
en ligne ou hors ligne.

Le lot couvre toutes les régions du monde (champ « region »). Ne te limite pas à l'Europe : un événement en Afrique, en Asie, en Amérique latine
ou au Moyen-Orient peut créer une opportunité sur place (clientèle locale ou diaspora) ou ailleurs. Indique toujours clairement le ou les pays visés.
Cherche activement la variété géographique des idées et la variété des types de business.

Exemples du type d'idée recherchée :
- un conflit éclate -> e-shop de kits de survie pour les pays voisins inquiets, ou dépôt-vente de groupes électrogènes dans une ville frontalière ;
- un grand site ou service ferme -> site de remplacement, outil de migration, comparatif d'alternatives ;
- une nouvelle loi entre en vigueur -> SaaS ou générateur pour se mettre en conformité, service local d'accompagnement, formation ;
- une pénurie ou une flambée des prix -> comparateur, alertes de disponibilité, import d'un produit introuvable, réparation ou location ;
- une tendance virale -> boutique de niche, stand ou food truck, atelier, événement.

Contraintes STRICTES :
1. Tout type de business est possible :
   - en ligne : site, e-commerce (dropshipping ou stock modeste inclus), SaaS, outil en ligne, contenu monétisé, marketplace, annuaire, communauté ;
   - hors ligne ou mixte : commerce physique, service local, import et négoce, production ou artisanat, restauration, événementiel, etc.
   Choisis la forme la plus adaptée à l'événement : une idée en ligne n'est pas préférée par défaut.
   « realisable_en_ligne » = true si l'activité se lance et s'exploite entièrement à distance, sans local ni présence sur place
   (la logistique confiée à un prestataire compte comme en ligne) ; false sinon.
2. Pas de plafond de budget : estime-le honnêtement, poste par poste. La note « cout » sert à exprimer qu'une idée coûte cher.
3. Lançable par UNE seule personne, en moins de 60 jours si « realisable_en_ligne » est vrai, en moins de 90 jours sinon.
4. Le porteur construit lui-même le site, l'application ou le SaaS avec une IA de développement (assistant de code type Claude Code ou Cursor),
   qui remplace le développeur freelance. Avec elle, un site vitrine, une boutique ou un outil simple se construit en 1 à 3 jours,
   un SaaS ou une plateforme plus riche en 1 à 2 semaines. Calcule la note « travail », le délai de lancement et la durée des étapes
   sur cette base : le temps restant porte sur ce que l'IA ne fait pas (contenus vérifiés, partenaires, fournisseurs, stock, démarches,
   local, premiers clients).
   Dans le budget : JAMAIS de coût de développeur (freelance, agence, prestataire). Mets en revanche une ligne « abonnement à l'IA de développement »
   pour les idées qui ont un site, une application ou un outil à construire : environ 20 € par mois pour un site simple, 100 € par mois pour un
   SaaS ou une plateforme, multiplié par le nombre de mois de construction (au moins un mois). Le reste du budget = les vrais frais
   (domaine, hébergement, API et services payants, publicité, contenus, juridique, stock, local, matériel, assurances, etc.).
5. Le lien entre l'événement et l'idée doit être direct et concret. Pas d'idées génériques qui existeraient sans l'événement.
6. Qualité plutôt que quantité : 0 à 8 idées par lot. Zéro idée est une réponse parfaitement acceptable si rien n'est vraiment exploitable.

Filtre éthique (obligatoire) — mets ethique.acceptable = false et explique pourquoi si l'idée :
- profite de la détresse de victimes (prix abusifs, revente spéculative de produits de première nécessité, arnaques aux dons) ;
- repose sur la désinformation, la peur artificielle, l'usurpation d'identité ou la contrefaçon ;
- contourne des sanctions, des lois ou facilite une activité illégale ou dangereuse (armes, drogues, etc.) ;
- vise des personnes vulnérables de façon manipulatrice.
Une idée qui AIDE réellement les personnes touchées (information fiable, mise en relation, outils utiles, produits à prix juste) est acceptable.

Déduplication : on te donne la liste des idées déjà proposées. Si une actualité renforce une idée existante, NE la recrée PAS : ajoute-la dans « renforcements » avec l'identifiant de l'idée. Ne propose pas deux fois la même idée dans un lot.

Notes de 0 à 10, TOUJOURS dans le sens « 10 = favorable pour l'entrepreneur » :
- potentiel : taille du marché et revenus possibles (10 = très fort) ;
- cout : budget de lancement (10 = moins de 100 €, 7 ≈ 1 000 €, 5 ≈ 5 000 €, 3 ≈ 20 000 €, 0 = 100 000 € ou plus) ;
- travail : effort pour lancer, développement fait avec l'IA (10 = un week-end, 5 ≈ 2-3 semaines, 0 = plusieurs mois) ;
- risque : risques juridiques, financiers, de réputation (10 = très faible risque) ;
- urgence : fenêtre d'opportunité (10 = à lancer dans les jours qui viennent, sinon trop tard) ;
- durabilite : l'activité tiendra-t-elle après l'actualité (10 = besoin durable) ;
- fiabilite : solidité de l'info et de la demande (10 = événement confirmé par plusieurs médias indépendants, demande évidente).
  Un sujet couvert par un seul média (nb_medias = 1, sans autres_sources) ne peut pas dépasser 6 en fiabilité ;
- concurrence : place disponible (10 = presque aucun concurrent).

Utilise UNIQUEMENT les références d'articles (A1, A2...) fournies dans « sources ». Cite toutes les références qui parlent du même événement.
Rédige TOUS les textes (titre, pitch, descriptions, étapes, risques, budget détaillé, explications des notes, etc.) en ANGLAIS américain naturel et clair :
les idées sont publiées pour un public international. Écris les montants en euros sous la forme « €1,500 ». Les clés JSON et les catégories restent inchangées.
« requete_verification » : 3 à 8 mots-clés en ANGLAIS, précis, qui permettent de retrouver d'autres articles sur l'événement déclencheur
dans Google News (noms propres, lieu, objet : ex. « Binance hack North Korea withdrawals »). Pas de guillemets ni d'opérateurs.

L'entrepreneur lit chaque idée en détail pour décider s'il se lance : sois complet, précis et concret (chiffres, lieux, dates, noms quand les articles les donnent), sans remplissage.
- « titre » : le nom du business en 60 caractères au plus, qui dit quoi et pour qui (ex. « Malware scanner for take-home coding tests »), sans sous-titre, sans l'événement déclencheur (il a son propre champ) et sans guillemets.
- « pitch » : 1 à 2 phrases d'accroche.
- « evenement_declencheur » : le titre de l'événement en une phrase.
- « contexte_declencheur » : 4 à 8 phrases. Ce qui s'est passé, où, quand, qui est touché, les chiffres clés, ce qui va probablement se passer ensuite, et pourquoi cela crée un besoin nouveau.
- « pourquoi_maintenant » : 2 à 4 phrases sur la fenêtre de tir et ce qui se passe si on attend.
- « description_detaillee » : 8 à 15 phrases. Le produit, le service ou le site concrètement (offre, fonctionnalités ou fonctionnement sur place), le parcours d'un client type, le positionnement, la façon d'attirer les premiers clients, le prix proposé et un ordre de grandeur réaliste du chiffre d'affaires possible.
- « notes_explications » : pour CHAQUE note, 2 à 3 phrases qui justifient le chiffre donné (sur quoi tu te bases, ce qui ferait monter ou baisser la note).
- « budget_detail » : la répartition du budget estimé, poste par poste avec montant (ex. « Nom de domaine + hébergement : 60 € »,
  « Abonnement à l'IA de développement (2 mois) : 40 € »), sans aucune ligne de développeur ou d'agence.
- « concurrents » : les concurrents ou alternatives existants connus (ou « aucun concurrent direct identifié »), avec en quoi l'idée se différencie.
- « etapes » : un plan d'action concret et ordonné (6 à 12 étapes), avec outils suggérés (IA de développement, Shopify, Stripe, etc. ; pour une activité sur place : statut, local,
  fournisseurs, autorisations, assurances) et la durée estimée de chaque étape.
- « risques » : chaque risque avec la façon de le limiter.
- « analyse » : ton avis global en 3 à 5 phrases (faut-il y aller, à quelles conditions, le principal point de vigilance)."""


def idea_schema() -> dict:
    score_props = {k: {"type": "integer"} for k in SCORE_KEYS}
    idea = {
        "type": "object",
        "properties": {
            "titre": {"type": "string"},
            "pitch": {"type": "string"},
            "evenement_declencheur": {"type": "string"},
            "contexte_declencheur": {"type": "string"},
            "pourquoi_maintenant": {"type": "string"},
            "description_detaillee": {"type": "string"},
            "categorie": {"type": "string", "enum": CATEGORIES},
            "realisable_en_ligne": {"type": "boolean"},
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
            "notes_explications": {
                "type": "object",
                "properties": {k: {"type": "string"} for k in SCORE_KEYS},
                "required": SCORE_KEYS,
                "additionalProperties": False,
            },
            "budget_detail": {"type": "array", "items": {"type": "string"}},
            "requete_verification": {"type": "string"},
            "concurrents": {"type": "array", "items": {"type": "string"}},
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
            "titre", "pitch", "evenement_declencheur", "contexte_declencheur", "pourquoi_maintenant",
            "description_detaillee", "notes_explications", "budget_detail", "requete_verification", "concurrents", "categorie", "realisable_en_ligne", "cible", "pays_cibles", "langues",
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
        {
            **{k: it[k] for k in ("ref", "titre", "resume", "langue", "pays", "region", "source", "date", "nb_medias") if it.get(k)},
            **({"autres_sources": [o["source"] for o in it["autres_sources"]]} if it.get("autres_sources") else {}),
        }
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
    system = SYSTEM_PROMPT
    request = dict(
        model=settings.model,
        max_tokens=64000,
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


TRIAGE_PROMPT = """Tu fais le PREMIER TRI d'actualités mondiales (toutes langues) pour des entrepreneurs qui cherchent des opportunités de business créées par un événement, en ligne (site, e-commerce, SaaS, outil, contenu) ou hors ligne (commerce, service local, import, artisanat, restauration, événementiel) : fermeture d'un service, pénurie, hausse de prix, nouvelle loi ou réglementation, conflit, catastrophe, épidémie, tendance virale, grève, sanctions, lancement ou panne d'un produit populaire, changement de comportement des consommateurs, etc.

Un modèle plus puissant analysera ensuite en détail les sujets que tu retiens. Ton rôle est seulement d'écarter le bruit évident (sport, faits divers isolés, people, résultats d'élections sans conséquence pratique, nécrologies...).

Règle d'or : en cas de doute, GARDE le sujet. Il vaut mieux garder un sujet inutile que rater une opportunité.
Garde des sujets de TOUTES les régions du monde (Afrique, Asie, Amérique latine, Moyen-Orient, Océanie, Amérique du Nord, Europe) : ne privilégie pas l'Europe.
Retiens au maximum {max_keep} références, classées de la plus prometteuse à la moins prometteuse. Réponds uniquement avec le JSON demandé."""


@dataclass
class TriageResult:
    refs: list[str]
    input_tokens: int = 0
    output_tokens: int = 0


def triage(settings: Settings, items: list[dict]) -> TriageResult:
    """Premier tri très bon marché (Claude Haiku) : ne garde que les sujets potentiellement exploitables."""
    if settings.dry_run or len(items) <= settings.max_articles_per_run:
        return TriageResult(refs=[it["ref"] for it in items])

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=3, timeout=300)
    lines = "\n".join(
        f"{it['ref']} | {it.get('region', '?')} | {it['titre']}" + (f" | {it['resume'][:120]}" if it.get("resume") else "")
        + (f" | {it['nb_medias']} médias" if it.get("nb_medias", 1) > 1 else "")
        for it in items
    )
    schema = {
        "type": "object",
        "properties": {"retenus": {"type": "array", "items": {"type": "string"}}},
        "required": ["retenus"],
        "additionalProperties": False,
    }
    with client.messages.stream(
        model=settings.triage_model,
        max_tokens=16000,
        system=TRIAGE_PROMPT.replace("{max_keep}", str(settings.triage_keep)),
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": "Sujets (référence | région | titre | résumé) :\n" + lines}],
    ) as stream:
        response = stream.get_final_message()
    if response.stop_reason in ("refusal", "max_tokens"):
        raise RuntimeError(f"Tri préalable interrompu ({response.stop_reason})")
    text = next((b.text for b in response.content if b.type == "text"), "")
    known = {it["ref"] for it in items}
    refs = [r for r in dict.fromkeys(json.loads(text).get("retenus", [])) if r in known]
    return TriageResult(refs=refs, input_tokens=response.usage.input_tokens or 0, output_tokens=response.usage.output_tokens or 0)
