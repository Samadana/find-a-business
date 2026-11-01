"""Recherche d'autres médias qui confirment l'événement à l'origine de chaque nouvelle idée.

Gratuit (Google News) et sans appel à Claude : Claude fournit pour chaque idée une courte requête
de vérification en anglais, on cherche les articles des 7 derniers jours et on ajoute ceux des
médias qui ne figurent pas encore dans les sources de l'idée.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import quote_plus

import feedparser
import requests

from .collect import USER_AGENT, _entry_date, clean_text

log = logging.getLogger(__name__)

EDITIONS = [("en-US", "US", "US:en")]


def search_google_news(session: requests.Session, query: str, timeout: float) -> list[dict]:
    out = []
    for hl, gl, ceid in EDITIONS:
        url = f"https://news.google.com/rss/search?q={quote_plus(query + ' when:7d')}&hl={hl}&gl={gl}&ceid={ceid}"
        try:
            resp = session.get(url, timeout=timeout)
            resp.raise_for_status()
        except requests.RequestException as exc:
            log.warning("Vérification impossible pour %r (%s)", query, exc)
            continue
        for entry in feedparser.parse(resp.content).entries[:30]:
            outlet = (entry.get("source") or {}).get("title") or ""
            title = clean_text(entry.get("title", ""), 250)
            if not outlet or not title or not entry.get("link"):
                continue
            published = _entry_date(entry) or datetime.now(timezone.utc)
            out.append({
                "titre": title, "url": entry["link"], "source": outlet, "langue": hl.split("-")[0],
                "date": published.isoformat(timespec="seconds"),
            })
    return out


def _outlet(source: str) -> str:
    return source.split("·")[-1].strip().lower()


def corroborate(ideas: list[dict], timeout: float, max_new: int = 5) -> int:
    """Ajoute jusqu'à `max_new` sources de médias différents à chaque idée. Retourne le nombre total ajouté."""
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    total = 0
    for idea in ideas:
        query = (idea.get("requete_verification") or "").strip()
        if not query:
            continue
        sources = idea.setdefault("sources", [])
        known_urls = {s["url"] for s in sources}
        known_outlets = {_outlet(s.get("source", "")) for s in sources}
        added = 0
        for art in search_google_news(session, query, timeout):
            if added >= max_new:
                break
            if art["url"] in known_urls or _outlet(art["source"]) in known_outlets:
                continue
            sources.append({**art, "confirmation": True})
            known_urls.add(art["url"])
            known_outlets.add(_outlet(art["source"]))
            added += 1
        idea["sources_confirmation"] = added
        total += added
    return total
