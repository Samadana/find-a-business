"""Notifications Discord (webhook gratuit)."""

from __future__ import annotations

import json
import logging
import time

import requests

log = logging.getLogger(__name__)

LABELS = {
    "potentiel": "Potentiel",
    "cout": "Coût",
    "travail": "Travail",
    "risque": "Risque",
    "urgence": "Urgence",
    "durabilite": "Durabilité",
    "fiabilite": "Fiabilité",
    "concurrence": "Concurrence",
}


SCORE_MEANING = {
    "potentiel": "10 = marché et revenus importants",
    "cout": "10 = presque gratuit, 0 = 5 000 € ou plus",
    "travail": "10 = lançable en un week-end",
    "risque": "10 = très faible risque",
    "urgence": "10 = à lancer dans les jours qui viennent",
    "durabilite": "10 = le besoin restera après l'actualité",
    "fiabilite": "10 = événement confirmé, demande évidente",
    "concurrence": "10 = quasiment aucun concurrent",
}


def color_for(score: float) -> int:
    if score >= 8:
        return 0x1F9D55  # vert
    if score >= 6.5:
        return 0x3B82F6  # bleu
    return 0xF59E0B  # orange


def _bar(value: int) -> str:
    return "▰" * value + "▱" * (10 - value)


def _cut(text: str, limit: int) -> str:
    text = str(text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _lines(items: list, limit: int, numbered: bool = False) -> str:
    out = "\n".join(f"{n}. {x}" if numbered else f"• {x}" for n, x in enumerate(items or [], 1))
    return _cut(out or "—", limit)


def _eur(n: int) -> str:
    return f"{n:,} €".replace(",", " ")


def build_idea_embeds(idea: dict, dashboard_url: str = "") -> list[dict]:
    """Une idée = 4 cartes Discord : présentation, déclencheur, notes expliquées, plan d'action."""
    color = color_for(idea["note_globale"])
    notes = idea["notes"]
    expl = idea.get("notes_explications") or {}
    url = f"{dashboard_url.rstrip('/')}/#{idea['id']}" if dashboard_url else None

    presentation = {
        "title": _cut(f"💡 {idea['titre']}", 256),
        "color": color,
        "description": _cut(
            f"**Note globale : {idea['note_globale']}/10**\n\n**{idea.get('pitch', '')}**\n\n"
            + (idea.get("description_detaillee") or ""),
            3000,
        ),
        "fields": [
            {"name": "Type", "value": _cut(idea.get("categorie", "?")
                                             + (" · en ligne" if idea.get("realisable_en_ligne", True) else " · sur place"), 100), "inline": True},
            {"name": "Budget estimé", "value": _eur(idea["budget_estime_eur"]), "inline": True},
            {"name": "Délai de lancement", "value": f"~{idea['delai_lancement_jours']} jours", "inline": True},
            {"name": "Fenêtre d'opportunité", "value": _cut(idea.get("duree_opportunite", "?"), 200), "inline": True},
            {"name": "Pays / langues", "value": _cut(", ".join(idea.get("pays_cibles", [])) + " · "
                                                     + ", ".join(idea.get("langues", [])), 200), "inline": True},
            {"name": "Cible", "value": _cut(idea.get("cible", "?"), 800), "inline": False},
            {"name": "Modèle de revenus", "value": _cut(idea.get("modele_revenus", "?"), 800), "inline": False},
        ],
    }
    if url:
        presentation["url"] = url

    sources = idea.get("sources", [])
    trigger = {
        "title": "📰 L'événement déclencheur",
        "color": color,
        "description": _cut(
            f"**{idea.get('evenement_declencheur', '')}**\n\n{idea.get('contexte_declencheur') or ''}"
            + (f"\n\n**Pourquoi maintenant :** {idea['pourquoi_maintenant']}" if idea.get("pourquoi_maintenant") else ""),
            2500,
        ),
        "fields": [{
            "name": f"Sources ({len(sources)})",
            "value": _cut("\n".join(f"[{_cut(s['titre'], 90)}]({s['url']}) · {s['source']}" for s in sources[:6]) or "—", 1024),
            "inline": False,
        }],
    }

    scores = {
        "title": "📊 Les notes expliquées (sur 10, 10 = favorable)",
        "color": color,
        "fields": [
            {
                "name": f"{label} : {notes[k]}/10  {_bar(notes[k])}",
                "value": _cut(f"{expl.get(k) or '—'}\n*({SCORE_MEANING[k]})*", 500),
                "inline": False,
            }
            for k, label in LABELS.items()
        ],
    }

    plan = {
        "title": "🛠️ Le travail à accomplir",
        "color": color,
        "description": _lines(idea.get("etapes", []), 2000, numbered=True),
        "fields": [
            {"name": "Budget détaillé", "value": _lines(idea.get("budget_detail", []), 700), "inline": False},
            {"name": "Concurrence", "value": _lines(idea.get("concurrents", []), 700), "inline": False},
            {"name": "Risques et parades", "value": _lines(idea.get("risques", []), 900), "inline": False},
            {"name": "Avis global", "value": _cut(idea.get("analyse", "—"), 700), "inline": False},
            {"name": "Éthique", "value": _cut((idea.get("ethique") or {}).get("raison", "—"), 300), "inline": False},
        ],
        "footer": {"text": "Find-a-Business"},
        "timestamp": idea.get("cree_le"),
    }
    return [presentation, trigger, scores, plan]


def _post(webhook_url: str, payload: dict, attachment: tuple[str, bytes] | None = None) -> bool:
    for attempt in range(4):
        try:
            if attachment:
                name, content = attachment
                resp = requests.post(
                    webhook_url,
                    data={"payload_json": json.dumps(payload)},
                    files={"files[0]": (name, content, "text/html")},
                    timeout=60,
                )
            else:
                resp = requests.post(webhook_url, json=payload, timeout=20)
        except requests.RequestException as exc:
            log.warning("Envoi Discord impossible (%s), essai %d", exc, attempt + 1)
            time.sleep(2 ** attempt)
            continue
        if resp.status_code == 429:
            retry = float(resp.json().get("retry_after", 2)) if resp.content else 2.0
            time.sleep(min(retry, 30))
            continue
        if resp.status_code >= 400:
            log.error("Discord a répondu %s : %s", resp.status_code, resp.text[:300])
            return False
        return True
    return False


def embed_size(embed: dict) -> int:
    """Nombre de caractères comptés par Discord (limite 6000 par message)."""
    size = len(embed.get("title", "")) + len(embed.get("description", ""))
    size += len(embed.get("footer", {}).get("text", ""))
    size += sum(len(f["name"]) + len(f["value"]) for f in embed.get("fields", []))
    return size


def group_embeds(embeds: list[dict], max_chars: int = 5800, max_count: int = 10) -> list[list[dict]]:
    groups: list[list[dict]] = []
    current: list[dict] = []
    total = 0
    for e in embeds:
        size = embed_size(e)
        if current and (total + size > max_chars or len(current) >= max_count):
            groups.append(current)
            current, total = [], 0
        current.append(e)
        total += size
    if current:
        groups.append(current)
    return groups


def send_ideas(
    webhook_url: str, ideas: list[dict], dashboard_url: str, test: bool = False,
    attachment: tuple[str, bytes] | None = None, header: str = "",
) -> int:
    """Envoie un message d'en-tête puis chaque idée en détail (un ou plusieurs messages par idée)."""
    if not webhook_url or not ideas:
        return 0
    ideas = sorted(ideas, key=lambda i: i["note_globale"], reverse=True)
    n = len(ideas)
    s = "s" if n > 1 else ""
    content = header or f"☀️ **Bilan du jour : {n} nouvelle{s} opportunité{s}**"
    if test:
        content = "🧪 **TEST** (idées fictives, le webhook fonctionne) · " + content
    _post(webhook_url, {"username": "Find-a-Business", "content": _cut(content, 1900)}, attachment)
    sent = 0
    for rank, idea in enumerate(ideas, 1):
        ok = True
        groups = group_embeds(build_idea_embeds(idea, dashboard_url))
        for gi, group in enumerate(groups):
            payload = {"username": "Find-a-Business", "embeds": group}
            if gi == 0:
                payload["content"] = f"**Idée {rank}/{n}**"
            ok = _post(webhook_url, payload) and ok
            time.sleep(1)
        if ok:
            idea["notifiee"] = True
            sent += 1
    return sent


def _below_text(below: list[dict], threshold: float) -> str:
    """Liste courte des idées trouvées mais sous la note minimale (détaillées seulement dans l'application)."""
    if not below:
        return ""
    below = sorted(below, key=lambda i: i["note_globale"], reverse=True)
    n = len(below)
    head = (f"📋 **{n} autre{'s' if n > 1 else ''} idée{'s' if n > 1 else ''} sous ta note minimale "
            f"({threshold:g}/10)**, à consulter en détail dans l'application :")
    lines = [f"• {i['note_globale']}/10 · {_cut(i['titre'], 150)}" for i in below[:15]]
    if n > 15:
        lines.append(f"… et {n - 15} autre(s)")
    return _cut(head + "\n" + "\n".join(lines), 1900)


def _rejected_text(rejected: list[dict]) -> str:
    """Idées écartées (filtre éthique, budget, sources) avec la raison, pour transparence."""
    if not rejected:
        return ""
    n = len(rejected)
    head = f"🚫 **{n} idée{'s' if n > 1 else ''} écartée{'s' if n > 1 else ''}** (détail dans l'onglet Écartées de l'application) :"
    lines = [f"• **{_cut(r.get('titre', '?'), 140)}**\n  ↳ {_cut(r.get('raison', '?'), 220)}" for r in rejected[:8]]
    if n > 8:
        lines.append(f"… et {n - 8} autre(s)")
    return _cut(head + "\n" + "\n".join(lines), 1900)


def send_daily_report(
    webhook_url: str, ideas: list[dict], run_info: dict, dashboard_url: str, test: bool = False,
    attachment: tuple[str, bytes] | None = None, below: list[dict] | None = None, threshold: float = 6.5,
    rejected: list[dict] | None = None,
) -> int:
    """Bilan du matin : envoyé chaque jour, avec le détail des nouvelles idées pertinentes s'il y en a."""
    if not webhook_url:
        return 0
    below_text = _below_text(below or [], threshold)
    rejected_text = _rejected_text(rejected or [])
    stats = (
        f"{run_info.get('sujets_analyses', 0)} sujets analysés sur {run_info.get('articles_nouveaux', 0)} nouveaux articles"
        f" · {run_info.get('idees_nouvelles', 0)} idée(s) trouvée(s) · {run_info.get('idees_ecartees', 0)} écartée(s)"
        + (f" · coût {run_info['cout_usd']:.2f} $" if run_info.get("cout_usd") else "")
    )
    if ideas:
        n = len(ideas)
        s = "s" if n > 1 else ""
        header = f"☀️ **Bilan du jour : {n} nouvelle{s} opportunité{s}** (note ≥ {threshold:g}/10)\n{stats}"
        sent = send_ideas(webhook_url, ideas, dashboard_url, test=test, attachment=attachment, header=header)
        for extra in (below_text, rejected_text):
            if extra:
                _post(webhook_url, {"username": "Find-a-Business", "content": extra})
        return sent
    if below:
        text = (f"☀️ **Bilan du jour** : aucune idée n'atteint ta note minimale ({threshold:g}/10) aujourd'hui.\n{stats}"
                f"\n\n{below_text}")
    else:
        text = f"☀️ **Bilan du jour** : aucune nouvelle idée trouvée aujourd'hui.\n{stats}"
    if test:
        text = "🧪 **TEST** · " + text
    _post(webhook_url, {"username": "Find-a-Business", "content": _cut(text, 1900)}, attachment)
    if rejected_text:
        _post(webhook_url, {"username": "Find-a-Business", "content": rejected_text})
    return 0


def send_text(webhook_url: str, text: str) -> bool:
    if not webhook_url:
        return False
    return _post(webhook_url, {"username": "Find-a-Business", "content": text[:1900]})
