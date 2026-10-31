"""Notifications Discord (webhook gratuit)."""

from __future__ import annotations

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


def color_for(score: float) -> int:
    if score >= 8:
        return 0x1F9D55  # vert
    if score >= 6.5:
        return 0x3B82F6  # bleu
    return 0xF59E0B  # orange


def _bar(value: int) -> str:
    return "▰" * value + "▱" * (10 - value)


def build_embed(idea: dict, dashboard_url: str) -> dict:
    notes = idea["notes"]
    score_lines = "\n".join(f"`{_bar(notes[k])}` {notes[k]:>2}/10 · {label}" for k, label in LABELS.items())
    steps = idea.get("etapes", [])[:3]
    steps_txt = "\n".join(f"{n}. {s[:150]}" for n, s in enumerate(steps, 1)) or "—"
    sources = idea.get("sources", [])[:3]
    sources_txt = "\n".join(f"[{s['source'][:40]}]({s['url']})" for s in sources) or "—"
    url = f"{dashboard_url.rstrip('/')}/#{idea['id']}" if dashboard_url else None

    embed = {
        "title": f"💡 {idea['titre']}"[:256],
        "description": (
            f"**Note globale : {idea['note_globale']}/10**\n\n{idea['pitch']}\n\n"
            f"**Déclencheur :** {idea['evenement_declencheur']}"
        )[:1500],
        "color": color_for(idea["note_globale"]),
        "fields": [
            {"name": "Type", "value": idea.get("categorie", "?"), "inline": True},
            {"name": "Budget estimé", "value": f"{idea['budget_estime_eur']:,} €".replace(",", " "), "inline": True},
            {"name": "Lancement", "value": f"~{idea['delai_lancement_jours']} jours", "inline": True},
            {"name": "Fenêtre", "value": str(idea.get("duree_opportunite", "?"))[:100], "inline": True},
            {"name": "Cible", "value": str(idea.get("cible", "?"))[:200], "inline": True},
            {"name": "Notes (10 = favorable)", "value": score_lines[:1024], "inline": False},
            {"name": "Premières étapes", "value": steps_txt[:1024], "inline": False},
            {"name": "Sources", "value": sources_txt[:1024], "inline": False},
        ],
        "footer": {"text": "Find-a-Business · détails et plan complet sur le tableau de bord"},
        "timestamp": idea.get("cree_le"),
    }
    if url:
        embed["url"] = url
    return embed


def _post(webhook_url: str, payload: dict) -> bool:
    for attempt in range(4):
        try:
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


def group_embeds(embeds: list[dict], max_chars: int = 5500, max_count: int = 10) -> list[list[dict]]:
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


def send_ideas(webhook_url: str, ideas: list[dict], dashboard_url: str, test: bool = False) -> int:
    """Envoie les idées en respectant les limites Discord (10 embeds et 6000 caractères par message)."""
    if not webhook_url or not ideas:
        return 0
    ideas = sorted(ideas, key=lambda i: i["note_globale"], reverse=True)
    by_embed = [(build_embed(i, dashboard_url), i) for i in ideas]
    lookup = {id(e): i for e, i in by_embed}
    sent = 0
    n = len(ideas)
    for index, group in enumerate(group_embeds([e for e, _ in by_embed])):
        payload = {"username": "Find-a-Business", "embeds": group}
        if index == 0:
            s = "s" if n > 1 else ""
            payload["content"] = f"☀️ **Bilan du jour : {n} nouvelle{s} opportunité{s}**"
            if dashboard_url:
                payload["content"] += f" · [Tableau de bord]({dashboard_url})"
            if test:
                payload["content"] = "🧪 **TEST** (idées fictives, le webhook fonctionne) · " + payload["content"]
        if _post(webhook_url, payload):
            for e in group:
                lookup[id(e)]["notifiee"] = True
                sent += 1
        time.sleep(1)
    return sent


def send_daily_report(webhook_url: str, ideas: list[dict], run_info: dict, dashboard_url: str, test: bool = False) -> int:
    """Bilan du matin : envoyé chaque jour, avec les nouvelles idées pertinentes s'il y en a."""
    if not webhook_url:
        return 0
    if ideas:
        return send_ideas(webhook_url, ideas, dashboard_url, test=test)
    lines = [
        "☀️ **Bilan du jour** : aucune nouvelle idée assez solide aujourd'hui.",
        f"{run_info.get('sujets_analyses', 0)} sujets analysés sur {run_info.get('articles_nouveaux', 0)} nouveaux articles"
        f" · {run_info.get('idees_nouvelles', 0)} idée(s) sous le seuil · {run_info.get('idees_ecartees', 0)} écartée(s).",
    ]
    if dashboard_url:
        lines.append(f"[Tableau de bord]({dashboard_url})")
    text = "\n".join(lines)
    if test:
        text = "🧪 **TEST** · " + text
    send_text(webhook_url, text)
    return 0


def send_text(webhook_url: str, text: str) -> bool:
    if not webhook_url:
        return False
    return _post(webhook_url, {"username": "Find-a-Business", "content": text[:1900]})
