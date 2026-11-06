"""Traitement des idées : validation, filtre éthique, notes, déduplication, fusion."""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

from .analyze import SCORE_KEYS
from .collect import normalize_title

log = logging.getLogger(__name__)

# Au-delà, le titre ne respecte pas la consigne (60 caractères) : on le signale, sans le tronquer.
TITLE_WARN_LEN = 90

# Poids de chaque note dans la note globale (somme avec TIMING_WEIGHT = 1).
# Urgence et durabilité s'opposent presque toujours : elles sont combinées en une seule note « timing »
# (voir timing_score), pour qu'une idée urgente OU durable ne soit pas pénalisée.
WEIGHTS = {
    "potentiel": 0.24,
    "fiabilite": 0.14,
    "cout": 0.11,
    "risque": 0.11,
    "concurrence": 0.10,
    "travail": 0.10,
}
TIMING_WEIGHT = 0.20

# Garde-fou éthique en plus du jugement de Claude : motifs explicitement interdits.
FORBIDDEN_PATTERNS = [
    r"\barnaque", r"\bescroquer", r"\bcontrefa[cç]on", r"\bfaux dons?\b", r"\bfausses? cagnottes?",
    r"\bd[ée]sinformation", r"\bfake news\b", r"\busurp", r"\bcontourner (les )?sanctions",
    r"\barmes? (à feu|de guerre)", r"\bmunitions?\b", r"\bdrogues?\b", r"\bpr[ie]x abusifs?",
    r"\bsp[ée]cul\w* sur (la|les) (p[ée]nurie|victimes)",
    # Les idées sont rédigées en anglais depuis novembre 2026 : mêmes motifs en anglais.
    r"\bscam", r"\bdefraud", r"\bcounterfeit", r"\bfake (donations?|fundrais\w*|charit\w*)", r"\bdisinformation",
    r"\bimpersonat", r"\b(evade|evading|circumvent\w*|bypass\w*) sanctions", r"\bfirearms?\b", r"\bammunition\b",
    r"\billegal drugs?\b", r"\bprice[- ]gouging", r"\bprofit\w* (from|on) (the )?(shortage|victims)",
]
FORBIDDEN_RE = re.compile("|".join(FORBIDDEN_PATTERNS), re.IGNORECASE)
# Un motif précédé de ces mots décrit une protection (« anti-arnaques », « éviter les arnaques »…), pas une pratique.
PROTECTIVE_RE = re.compile(
    r"(anti[- ]?|contre (les |la |le |l')?|[ée]viter (les |la |le |l')?|d[ée]tect\w* (les |la |le |l')?|"
    r"rep[ée]r\w* (les |la |le |l')?|signal\w* (les |la |le |l')?|lutt\w* contre (les |la |le |l')?|"
    r"prot[ée]g\w* (des |de la |du |de l'|contre (les |la |le |l')?)|pr[ée]vention (des |de la |du |de l')?|"
    r"v[ée]rifi\w* (les |la |le |l')?|alerte\w* (aux |sur les )?|"
    r"against (the )?|avoid\w* (the )?|detect\w* (the )?|spot\w* (the )?|report\w* (the )?|fight\w* (against )?(the )?|"
    r"protect\w* (from |against )?(the )?|prevent\w* (the )?|verif\w* (the )?|alert\w* (on |about )?(the )?)$",
    re.IGNORECASE,
)


def forbidden_match(text: str) -> str | None:
    """Premier motif interdit employé comme pratique (et non comme protection), sinon None."""
    for m in FORBIDDEN_RE.finditer(text):
        before = text[max(0, m.start() - 40):m.start()]
        if not PROTECTIVE_RE.search(before):
            return m.group(0)
    return None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clamp_scores(notes: dict) -> dict:
    out = {}
    for k in SCORE_KEYS:
        try:
            out[k] = max(0, min(10, int(notes.get(k, 0))))
        except (TypeError, ValueError):
            out[k] = 0
    return out


def timing_score(notes: dict) -> float:
    """0,7 × la meilleure note entre urgence et durabilité + 0,3 × l'autre."""
    u, d = notes["urgence"], notes["durabilite"]
    return 0.7 * max(u, d) + 0.3 * min(u, d)


def global_score(notes: dict, signals: int = 1) -> float:
    base = sum(notes[k] * w for k, w in WEIGHTS.items()) + TIMING_WEIGHT * timing_score(notes)
    bonus = min(0.5, 0.1 * max(0, signals - 1))  # une idée confirmée par plusieurs actualités monte un peu
    return round(min(10.0, base + bonus), 1)


def make_id(title: str) -> str:
    return "idee-" + hashlib.sha1(f"{normalize_title(title)}|{now_iso()[:10]}".encode()).hexdigest()[:8]


def resolve_sources(refs: list[str], items_by_ref: dict[str, dict], limit: int = 12) -> list[dict]:
    """Articles cités par Claude, puis les autres médias qui couvrent les mêmes sujets."""
    out, seen = [], set()
    cited = [items_by_ref[r] for r in (str(x).strip() for x in refs) if r in items_by_ref]
    for it in cited:
        if it["url"] not in seen:
            seen.add(it["url"])
            out.append({k: it.get(k, "") for k in ("titre", "url", "source", "langue", "date")})
    for it in cited:
        for other in it.get("autres_sources", []) or []:
            if len(out) >= limit:
                return out
            if other["url"] not in seen:
                seen.add(other["url"])
                out.append({k: other.get(k, "") for k in ("titre", "url", "source", "langue", "date")})
    return out[:limit] if len(out) > limit else out


def ethics_check(idea: dict) -> tuple[bool, str]:
    eth = idea.get("ethique") or {}
    if not eth.get("acceptable", False):
        return False, eth.get("raison") or "Jugée non éthique par l'analyse."
    text = " ".join(str(idea.get(k, "")) for k in ("titre", "pitch", "modele_revenus", "analyse"))
    match = forbidden_match(text)
    if match:
        return False, f"Motif interdit détecté : « {match} »."
    return True, eth.get("raison", "")


def similarity(a: dict, b: dict) -> float:
    ta, tb = normalize_title(a.get("titre", "")), normalize_title(b.get("titre", ""))
    title_ratio = SequenceMatcher(None, ta, tb).ratio()
    ka = {normalize_title(k) for k in a.get("mots_cles", []) if k}
    kb = {normalize_title(k) for k in b.get("mots_cles", []) if k}
    kw = len(ka & kb) / len(ka | kb) if ka and kb else 0.0
    return max(title_ratio, kw)


def find_duplicate(candidate: dict, ideas: list[dict], threshold: float = 0.72) -> dict | None:
    best, best_score = None, 0.0
    for idea in ideas:
        s = similarity(candidate, idea)
        if s > best_score:
            best, best_score = idea, s
    return best if best_score >= threshold else None


def reinforce(idea: dict, sources: list[dict], comment: str = "") -> None:
    known = {s["url"] for s in idea.get("sources", [])}
    new = [s for s in sources if s["url"] not in known]
    idea.setdefault("sources", []).extend(new)
    idea["signaux"] = idea.get("signaux", 1) + 1
    idea["mis_a_jour_le"] = now_iso()
    idea["dernier_signal_le"] = idea["mis_a_jour_le"]
    idea["statut"] = "active"
    if comment:
        idea.setdefault("historique", []).append({"date": now_iso(), "note": comment})
        idea["historique"] = idea["historique"][-10:]
    idea["note_globale"] = global_score(idea["notes"], idea["signaux"])


# Le porteur développe lui-même avec une IA de développement : aucun coût de développeur externe dans les budgets.
# L'abonnement à l'IA de développement, lui, est un vrai frais et reste dans le budget.
_AI = r"(?:\b(?:IA|AI)\b|claude|cursor|copilot|chatgpt|windsurf|lovable|bolt\.new)"
_SUB = r"(?:abonnement|subscription|plan\b|forfait|licen[cs]e)"
AI_TOOL_RE = re.compile(rf"{_AI}.*{_SUB}|{_SUB}.*{_AI}", re.IGNORECASE)
DEV_COST_RE = re.compile(
    r"d[ée]velopp|develop(?:er|ment)|programm|codage|coding|\bdev\b|int[ée]grateur|agence (?:web|digitale)|"
    r"(?:web|digital|development) agency",
    re.IGNORECASE,
)
# « 1 500 € » (français) ou « €1,500 » (anglais).
AMOUNT_RE = re.compile(r"€\s*(\d[\d\s\u202f\u00a0.,]*\d|\d)|(\d[\d\s\u202f\u00a0.,]*\d|\d)\s*(?:€|EUR\b)")


def _amount(line: str) -> int:
    m = AMOUNT_RE.findall(line)
    if not m:
        return 0
    raw = next(g for g in m[-1] if g)
    raw = re.sub(r"[.,]\d{2}$", "", raw.strip())  # ignore les centimes
    digits = re.sub(r"[^\d]", "", raw)
    return int(digits) if digits else 0


def strip_dev_costs(idea: dict) -> int:
    """Retire du budget détaillé les lignes de développement sous-traité et ajuste le budget estimé.

    Retourne le montant retiré.
    """
    kept, removed = [], 0
    for line in idea.get("budget_detail") or []:
        if DEV_COST_RE.search(line) and not AI_TOOL_RE.search(line):
            removed += _amount(line)
        else:
            kept.append(line)
    if len(kept) != len(idea.get("budget_detail") or []):
        idea["budget_detail"] = kept
        idea["budget_estime_eur"] = max(0, int(idea.get("budget_estime_eur", 0) or 0) - removed)
    return removed


def process_analysis(
    data: dict,
    items: list[dict],
    ideas: list[dict],
    max_budget_eur: int = 0,
) -> tuple[list[dict], list[dict], int]:
    """Intègre la réponse de Claude dans la base d'idées.

    `max_budget_eur` : 0 = pas de plafond (réglage par défaut depuis l'ouverture à tous les types d'idées).
    Retourne (nouvelles_idées, idées_écartées, nb_renforcements). `ideas` est modifiée sur place.
    """
    items_by_ref = {it["ref"]: it for it in items}
    by_id = {i["id"]: i for i in ideas}
    new_ideas, rejected = [], []
    reinforced = 0

    for r in data.get("renforcements", []) or []:
        target = by_id.get(r.get("idee_id", ""))
        if target:
            reinforce(target, resolve_sources(r.get("sources", []), items_by_ref), r.get("commentaire", ""))
            reinforced += 1

    for raw in data.get("idees", []) or []:
        idea = dict(raw)
        titre = str(idea.get("titre", ""))
        if len(titre) > TITLE_WARN_LEN:
            log.warning("Titre trop long (%d caractères) : %r", len(titre), titre)
        idea["notes"] = clamp_scores(raw.get("notes", {}))
        idea["sources"] = resolve_sources(raw.get("sources", []), items_by_ref)
        idea["budget_estime_eur"] = max(0, int(raw.get("budget_estime_eur", 0) or 0))
        idea["delai_lancement_jours"] = max(0, int(raw.get("delai_lancement_jours", 0) or 0))
        strip_dev_costs(idea)

        ok, reason = ethics_check(idea)
        idea["realisable_en_ligne"] = bool(raw.get("realisable_en_ligne", True))
        if ok and max_budget_eur > 0 and idea["budget_estime_eur"] > max_budget_eur:
            ok, reason = False, f"Budget estimé {idea['budget_estime_eur']} € > {max_budget_eur} €."
        if ok and not idea["sources"]:
            ok, reason = False, "Aucune source vérifiable associée."
        if not ok:
            rejected.append({
                "titre": idea.get("titre", "?"),
                "pitch": idea.get("pitch", ""),
                "raison": reason,
                "sources": idea["sources"],
                "date": now_iso(),
            })
            continue

        dup = find_duplicate(idea, ideas + new_ideas)
        if dup is not None:
            reinforce(dup, idea["sources"], "Nouvelle actualité liée (doublon détecté automatiquement).")
            reinforced += 1
            continue

        idea.update({
            "id": make_id(idea["titre"]),
            "signaux": 1,
            "cree_le": now_iso(),
            "mis_a_jour_le": now_iso(),
            "dernier_signal_le": now_iso(),
            "statut": "active",
            "notifiee": False,
            "langue_redaction": "en",
        })
        idea["note_globale"] = global_score(idea["notes"], 1)
        new_ideas.append(idea)

    ideas.extend(new_ideas)
    return new_ideas, rejected, reinforced


def _parse_utc(value: str) -> datetime | None:
    """Date ISO -> datetime avec fuseau (UTC si absent) ; None si illisible."""
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _signals(idea: dict) -> int:
    try:
        return max(1, int(idea.get("signaux") or 1))
    except (TypeError, ValueError):
        return 1


def archive_old(ideas: list[dict], days: int) -> int:
    """Archive les idées actives sans nouvelle actualité depuis `days` jours.

    Se base sur `dernier_signal_le` (création ou dernier renforcement) : un simple recalcul de la note,
    qui avance `mis_a_jour_le`, ne retarde pas l'archivage.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    count = 0
    for idea in ideas:
        if idea.get("statut") != "active":
            continue
        last = _parse_utc(idea.get("dernier_signal_le") or idea.get("mis_a_jour_le") or "")
        if last is not None and last < cutoff:
            idea["statut"] = "archivee"
            count += 1
    return count


def rescore(ideas: list[dict]) -> int:
    """Recalcule la note globale des idées actives avec la formule actuelle. Retourne le nombre d'idées renotées.

    Une idée renotée voit `mis_a_jour_le` avancer (sinon SeedFox l'ignore) ; `dernier_signal_le` garde
    l'ancienne date pour que l'archivage n'en soit pas retardé.
    """
    count = 0
    for idea in ideas:
        if idea.get("statut") != "active" or not isinstance(idea.get("notes"), dict):
            continue
        score = global_score(clamp_scores(idea["notes"]), _signals(idea))
        if score == idea.get("note_globale"):
            continue
        if not idea.get("dernier_signal_le") and idea.get("mis_a_jour_le"):
            idea["dernier_signal_le"] = idea["mis_a_jour_le"]
        idea["mis_a_jour_le"] = now_iso()
        idea["note_globale"] = score
        count += 1
    return count


def recent_ideas_for_prompt(ideas: list[dict], limit: int = 100) -> list[dict]:
    active = [i for i in ideas if i.get("statut") == "active"]
    active.sort(key=lambda i: i["mis_a_jour_le"], reverse=True)
    return active[:limit]
