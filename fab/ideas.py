"""Traitement des idées : validation, filtre éthique, notes, déduplication, fusion."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

from .analyze import SCORE_KEYS
from .collect import normalize_title

# Poids de chaque note dans la note globale (somme = 1).
WEIGHTS = {
    "potentiel": 0.22,
    "fiabilite": 0.16,
    "durabilite": 0.14,
    "risque": 0.12,
    "cout": 0.10,
    "travail": 0.10,
    "concurrence": 0.10,
    "urgence": 0.06,
}

# Garde-fou éthique en plus du jugement de Claude : motifs explicitement interdits.
FORBIDDEN_PATTERNS = [
    r"\barnaque", r"\bescroquer", r"\bcontrefa[cç]on", r"\bfaux dons?\b", r"\bfausses? cagnottes?",
    r"\bd[ée]sinformation", r"\bfake news\b", r"\busurp", r"\bcontourner (les )?sanctions",
    r"\barmes? (à feu|de guerre)", r"\bmunitions?\b", r"\bdrogues?\b", r"\bpr[ie]x abusifs?",
    r"\bsp[ée]cul\w* sur (la|les) (p[ée]nurie|victimes)",
]
FORBIDDEN_RE = re.compile("|".join(FORBIDDEN_PATTERNS), re.IGNORECASE)


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


def global_score(notes: dict, signals: int = 1) -> float:
    base = sum(notes[k] * w for k, w in WEIGHTS.items())
    bonus = min(0.5, 0.1 * max(0, signals - 1))  # une idée confirmée par plusieurs actualités monte un peu
    return round(min(10.0, base + bonus), 1)


def make_id(title: str) -> str:
    return "idee-" + hashlib.sha1(f"{normalize_title(title)}|{now_iso()[:10]}".encode()).hexdigest()[:8]


def resolve_sources(refs: list[str], items_by_ref: dict[str, dict]) -> list[dict]:
    out, seen = [], set()
    for ref in refs:
        it = items_by_ref.get(str(ref).strip())
        if not it or it["url"] in seen:
            continue
        seen.add(it["url"])
        out.append({k: it[k] for k in ("titre", "url", "source", "langue", "date")})
    return out


def ethics_check(idea: dict) -> tuple[bool, str]:
    eth = idea.get("ethique") or {}
    if not eth.get("acceptable", False):
        return False, eth.get("raison") or "Jugée non éthique par l'analyse."
    text = " ".join(str(idea.get(k, "")) for k in ("titre", "pitch", "modele_revenus", "analyse"))
    match = FORBIDDEN_RE.search(text)
    if match:
        return False, f"Motif interdit détecté : « {match.group(0)} »."
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
    idea["statut"] = "active"
    if comment:
        idea.setdefault("historique", []).append({"date": now_iso(), "note": comment})
        idea["historique"] = idea["historique"][-10:]
    idea["note_globale"] = global_score(idea["notes"], idea["signaux"])


# Le porteur de projet développe lui-même : aucun coût de développement externe dans les budgets.
DEV_COST_RE = re.compile(
    r"d[ée]velopp|developer|programm|codage|\bdev\b|int[ée]grateur|agence (?:web|digitale)",
    re.IGNORECASE,
)
AMOUNT_RE = re.compile(r"(\d[\d\s\u202f\u00a0.]*)\s*€")


def _amount(line: str) -> int:
    m = AMOUNT_RE.findall(line)
    if not m:
        return 0
    digits = re.sub(r"[^\d]", "", m[-1])
    return int(digits) if digits else 0


def strip_dev_costs(idea: dict) -> int:
    """Retire du budget détaillé les lignes de développement sous-traité et ajuste le budget estimé.

    Retourne le montant retiré.
    """
    kept, removed = [], 0
    for line in idea.get("budget_detail") or []:
        if DEV_COST_RE.search(line):
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
    max_budget_eur: int,
) -> tuple[list[dict], list[dict], int]:
    """Intègre la réponse de Claude dans la base d'idées.

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
        idea["notes"] = clamp_scores(raw.get("notes", {}))
        idea["sources"] = resolve_sources(raw.get("sources", []), items_by_ref)
        idea["budget_estime_eur"] = max(0, int(raw.get("budget_estime_eur", 0) or 0))
        idea["delai_lancement_jours"] = max(0, int(raw.get("delai_lancement_jours", 0) or 0))
        strip_dev_costs(idea)

        ok, reason = ethics_check(idea)
        if ok and idea["budget_estime_eur"] > max_budget_eur:
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
            "statut": "active",
            "notifiee": False,
        })
        idea["note_globale"] = global_score(idea["notes"], 1)
        new_ideas.append(idea)

    ideas.extend(new_ideas)
    return new_ideas, rejected, reinforced


def archive_old(ideas: list[dict], days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    count = 0
    for idea in ideas:
        if idea.get("statut") == "active" and datetime.fromisoformat(idea["mis_a_jour_le"]) < cutoff:
            idea["statut"] = "archivee"
            count += 1
    return count


def recent_ideas_for_prompt(ideas: list[dict], limit: int = 100) -> list[dict]:
    active = [i for i in ideas if i.get("statut") == "active"]
    active.sort(key=lambda i: i["mis_a_jour_le"], reverse=True)
    return active[:limit]
