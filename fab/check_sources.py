"""Vérification gratuite des sources (aucun appel à Claude) : nombre d'articles par source et par région.

Usage : python -m fab.check_sources
"""

from __future__ import annotations

import json
import logging
import time
from collections import Counter

from .collect import build_feed_list, fetch_gdelt, fetch_rss, filter_recent
from .config import ROOT, Settings
from .selection import merge_triage, select_for_analysis


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    settings = Settings()
    sources = json.loads((ROOT / "config" / "sources.json").read_text(encoding="utf-8"))
    feeds = build_feed_list(sources)
    print(f"{len(feeds)} flux RSS + {len(sources.get('gdelt_queries', []))} requêtes GDELT\n")
    dead = []
    articles = []
    for feed in feeds:
        arts, fail = fetch_rss([feed], settings.http_timeout)
        articles += arts
        status = "ÉCHEC" if fail else f"{len(arts):4d}"
        if fail or not arts:
            dead.append(feed["name"])
        print(f"{status}  {feed['name']}")
    for i, q in enumerate(sources.get("gdelt_queries", [])):
        if i:
            time.sleep(6)
        arts, fail = fetch_gdelt([q], settings.http_timeout)
        articles += arts
        print(f"{'ÉCHEC' if fail else f'{len(arts):4d}'}  GDELT {q[:90]}")
        if fail or not arts:
            dead.append("GDELT " + q[:60])
    recent = filter_recent(articles, settings.max_article_age_hours)
    print(f"\nArticles récents : {len(recent)} sur {len(articles)}")
    print("Par région (articles) :", dict(Counter(a.region or "?" for a in recent).most_common()))
    candidates = select_for_analysis(recent, settings.triage_candidates)
    print("Par région (sujets candidats) :", dict(Counter(c["region"] for c in candidates).most_common()))
    final = merge_triage(candidates, [c["ref"] for c in candidates], settings.always_keep, settings.max_articles_per_run)
    print("Par région (sujets envoyés à l'analyse, sans le tri Haiku) :", dict(Counter(c["region"] for c in final).most_common()))
    print(f"\nSources muettes ou en échec ({len(dead)}) :")
    for name in dead:
        print("  -", name)


if __name__ == "__main__":
    main()
