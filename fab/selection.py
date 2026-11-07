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
from .regions import region_of

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
    "escassez", "aumento", "proibicao", "tarifa", "inflacion", "inflacao", "apagon", "apagao",
    # néerlandais / polonais / turc / indonésien / vietnamien / swahili (sans accents)
    "tekort", "sluiting", "wet", "staking", "niedobor", "zamkniecie", "ustawa", "strajk",
    "kitlik", "kapanis", "yasak", "zam", "grev", "kelangkaan", "penutupan", "larangan", "kenaikan", "mogok",
    "thieu", "dong", "cam", "luat", "uhaba", "marufuku", "mgomo", "bei",
    # russe / ukrainien
    "дефицит", "закрытие", "закон", "запрет", "забастовка", "кризис", "цены", "санкции", "війна", "дефіцит",
    # arabe / hébreu / persan
    "نقص", "إغلاق", "قانون", "حظر", "إضراب", "أزمة", "ارتفاع", "حرب", "عقوبات", "מחסור", "סגירה", "חוק",
    # hindi
    "कमी", "बंद", "कानून", "प्रतिबंध", "हड़ताल", "संकट", "महंगाई",
}

# Langues écrites sans espaces (chinois, japonais, thaï) : recherche par sous-chaîne.
TRIGGER_SUBSTRINGS = {
    "品薄", "不足", "終了", "閉鎖", "新法", "規制", "値上げ", "禁止", "戦争", "停電", "地震", "ストライキ", "物価",
    "短缺", "关闭", "关停", "新规", "法规", "涨价", "禁令", "战争", "罢工", "危机", "停产",
    "품귀", "종료", "폐쇄", "규제", "인상", "금지", "전쟁", "파업", "위기",
    "ขาดแคลน", "ปิด", "กฎหมาย", "ขึ้นราคา",
}


def trigger_hits(tokens: set[str], text: str) -> int:
    return len(tokens & TRIGGER_WORDS) + sum(1 for t in TRIGGER_SUBSTRINGS if t in text)


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

    @property
    def region(self) -> str:
        lead = self.lead
        return lead.region or region_of(lead.country, lead.lang)

    def priority(self, now: datetime) -> float:
        n_sources = len(self.sources)
        hits = trigger_hits(self.tokens, " ".join(a.title for a in self.articles[:5]))
        newest = max(datetime.fromisoformat(a.published) for a in self.articles)
        age_h = max((now - newest).total_seconds() / 3600, 0)
        recency = max(0.0, 1.0 - age_h / 36)
        return min(n_sources, 6) * 1.0 + min(hits, 3) * 1.5 + recency * 2.0


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


def interleave_regions(items: list, region_key) -> list:
    """Réordonne une liste triée par priorité en alternant les régions du monde.

    Chaque région garde son ordre interne ; on prend à tour de rôle le meilleur sujet restant de chaque
    région. Les régions très couvertes (Europe, Amérique du Nord) ne monopolisent donc plus le haut de la liste.
    """
    groups: dict[str, list] = defaultdict(list)
    order: list[str] = []
    for it in items:
        r = region_key(it)
        if r not in groups:
            order.append(r)
        groups[r].append(it)
    out = []
    depth = 0
    while len(out) < len(items):
        for r in order:
            if depth < len(groups[r]):
                out.append(groups[r][depth])
        depth += 1
    return out


def _other_sources(c: Cluster, limit: int = 4) -> list[dict]:
    """Autres médias qui couvrent le même sujet (un par média), pour étoffer les sources des idées."""
    seen = {c.lead.source}
    out = []
    for a in c.articles[1:]:
        if a.source in seen:
            continue
        seen.add(a.source)
        out.append({"titre": a.title, "url": a.url, "source": a.source, "langue": a.lang, "date": a.published})
        if len(out) >= limit:
            break
    return out


def select_for_analysis(articles: list[Article], max_items: int, max_per_source: int = 15) -> list[dict]:
    """Retourne au plus `max_items` sujets, prêts à être envoyés à Claude, en alternant les régions du monde."""
    now = datetime.now(timezone.utc)
    clusters = cluster_articles(articles)
    clusters.sort(key=lambda c: c.priority(now), reverse=True)
    clusters = interleave_regions(clusters, lambda c: c.region)

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
                "region": c.region,
                "source": lead.source,
                "date": lead.published,
                "nb_medias": len(c.sources),
                "url": lead.url,
                "ids": [a.id for a in c.articles],
                "autres_sources": _other_sources(c),
            }
        )
        if len(selected) >= max_items:
            break
    return selected


def merge_triage(
    candidates: list[dict], triage_refs: list[str], always_keep: int, max_items: int, max_share: float = 0.3,
) -> list[dict]:
    """Sujets envoyés à l'analyse finale : ceux retenus par le tri + les mieux classés par l'heuristique.

    Le filet de sécurité (`always_keep`) garantit que les sujets les plus repris par les médias
    et contenant des mots déclencheurs passent toujours, même si le tri les a écartés.
    """
    by_ref = {c["ref"]: c for c in candidates}
    # Aucune région ne peut occuper plus de 30 % de l'analyse finale, tant que d'autres régions ont des sujets.
    cap = max(1, int(max_items * max_share))
    per_region: Counter = Counter()
    chosen: list[str] = []
    overflow: list[str] = []
    for ref in [c["ref"] for c in candidates[:always_keep]] + list(triage_refs):
        if ref not in by_ref or ref in chosen or ref in overflow:
            continue
        region = by_ref[ref].get("region", "monde")
        if per_region[region] >= cap:
            overflow.append(ref)
            continue
        per_region[region] += 1
        chosen.append(ref)
        if len(chosen) >= max_items:
            break
    for ref in overflow:
        if len(chosen) >= max_items:
            break
        chosen.append(ref)
    return [by_ref[r] for r in chosen]


def split_batches(items: list[dict], n_batches: int) -> list[list[dict]]:
    """Répartit les sujets retenus en lots d'analyse qui mélangent chacun toutes les régions.

    Les sujets sont groupés par région (ordre de priorité gardé), puis distribués aux lots avec un compteur
    global qui continue d'une région à l'autre : chaque lot reçoit sa part de chaque région.
    Taille d'un lot : arrondi supérieur de total / lots. Les lots vides sont retirés.
    """
    n = max(1, n_batches)
    groups: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        groups[it.get("region", "monde")].append(it)
    batches: list[list[dict]] = [[] for _ in range(n)]
    k = 0
    for group in groups.values():
        for it in group:
            batches[k % n].append(it)
            k += 1
    return [b for b in batches if b]
