"""Regroupement des articles qui parlent du même sujet et choix des plus prometteurs.

L'objectif est d'envoyer à Claude un panel varié et compact (coût maîtrisé),
en favorisant les sujets repris par plusieurs médias et ceux qui contiennent
des « mots déclencheurs » (pénurie, fermeture, nouvelle loi, guerre...).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .collect import Article, normalize_title

# Mots déclencheurs multilingues (en minuscules, sans accents).
TRIGGER_WORDS = {
    # anglais
    "shortage", "shutdown", "shutting", "discontinued", "closure", "closing", "ban", "banned",
    "outage", "recall", "law", "regulation", "tariff", "war", "evacuation", "blackout",
    "earthquake", "flood", "wildfire", "heatwave", "strike", "price", "prices", "surge",
    "crisis", "launch", "deadline", "subsidy", "bankrupt", "bankruptcy", "layoffs", "sanctions",
    "boycott", "viral", "trend", "record", "epidemic", "outbreak", "drought", "inflation",
    # français
    "penurie", "fermeture", "ferme", "interdiction", "interdit", "loi", "reforme", "guerre",
    "greve", "crise", "faillite", "hausse", "prix", "canicule", "inondation", "seisme",
    "panne", "rappel", "aide", "subvention", "liquidation", "boycott", "taxe",
    # allemand / espagnol / italien / portugais
    "engpass", "schliessung", "gesetz", "krieg", "streik", "krise", "verbot",
    "escasez", "cierre", "ley", "guerra", "huelga", "crisis", "prohibicion",
    "carenza", "chiusura", "legge", "sciopero", "falta", "fechamento", "lei", "greve",
}


@dataclass
class Cluster:
    articles: list[Article] = field(default_factory=list)
    tokens: set[str] = field(default_factory=set)

    @property
    def lead(self) -> Article:
        return self.articles[0]

    @property
    def sources(self) -> set[str]:
        return {a.source for a in self.articles}

    def priority(self, now: datetime) -> float:
        n_sources = len(self.sources)
        trigger_hits = len(self.tokens & TRIGGER_WORDS)
        newest = max(datetime.fromisoformat(a.published) for a in self.articles)
        age_h = max((now - newest).total_seconds() / 3600, 0)
        recency = max(0.0, 1.0 - age_h / 36)
        return min(n_sources, 6) * 1.0 + min(trigger_hits, 3) * 1.5 + recency * 2.0


def _tokens(article: Article) -> set[str]:
    return {t for t in normalize_title(article.title).split() if len(t) >= 3}


def cluster_articles(articles: list[Article], threshold: float = 0.5) -> list[Cluster]:
    """Regroupe les titres proches (similarité de Jaccard sur les mots)."""
    unique: dict[str, Article] = {}
    for a in articles:
        unique.setdefault(a.id, a)

    clusters: list[Cluster] = []
    index: dict[str, set[int]] = defaultdict(set)
    for article in unique.values():
        toks = _tokens(article)
        if not toks:
            continue
        candidates = Counter()
        for t in toks:
            for ci in index[t]:
                candidates[ci] += 1
        best, best_score = None, 0.0
        for ci, shared in candidates.most_common(20):
            union = len(toks | clusters[ci].tokens)
            score = shared / union if union else 0
            if score > best_score:
                best, best_score = ci, score
        if best is not None and best_score >= threshold:
            clusters[best].articles.append(article)
            clusters[best].tokens |= toks
            for t in toks:
                index[t].add(best)
        else:
            clusters.append(Cluster(articles=[article], tokens=set(toks)))
            for t in toks:
                index[t].add(len(clusters) - 1)
    return clusters


def select_for_analysis(articles: list[Article], max_items: int, max_per_source: int = 15) -> list[dict]:
    """Retourne au plus `max_items` sujets, prêts à être envoyés à Claude."""
    now = datetime.now(timezone.utc)
    clusters = cluster_articles(articles)
    clusters.sort(key=lambda c: c.priority(now), reverse=True)

    per_source: Counter = Counter()
    selected = []
    for c in clusters:
        lead = c.lead
        if per_source[lead.source] >= max_per_source:
            continue
        per_source[lead.source] += 1
        selected.append(
            {
                "ref": f"A{len(selected) + 1}",
                "titre": lead.title,
                "resume": lead.summary,
                "langue": lead.lang,
                "pays": lead.country,
                "source": lead.source,
                "date": lead.published,
                "nb_medias": len(c.sources),
                "url": lead.url,
                "ids": [a.id for a in c.articles],
            }
        )
        if len(selected) >= max_items:
            break
    return selected
