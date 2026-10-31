"""Collecte des actualités mondiales (flux RSS, Google News par pays, GDELT)."""

from __future__ import annotations

import calendar
import hashlib
import html
import json
import logging
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

import feedparser
import requests

log = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; FindABusinessBot/1.0; +https://github.com)"
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


@dataclass
class Article:
    id: str
    title: str
    summary: str
    url: str
    source: str
    lang: str
    published: str  # ISO 8601 UTC
    country: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def clean_text(text: str, limit: int = 300) -> str:
    text = html.unescape(TAG_RE.sub(" ", text or ""))
    text = SPACE_RE.sub(" ", text).strip()
    return text[:limit].rstrip() + ("…" if len(text) > limit else "")


def normalize_title(title: str) -> str:
    """Titre simplifié pour comparer deux articles (accents, ponctuation, casse)."""
    title = unicodedata.normalize("NFKD", title.lower())
    title = "".join(c for c in title if not unicodedata.combining(c))
    # Google News ajoute " - Nom du média" à la fin des titres
    title = re.sub(r"\s[-–|]\s[^-–|]{2,40}$", "", title)
    title = re.sub(r"[^\w\s]", " ", title)
    return SPACE_RE.sub(" ", title).strip()


def article_id(url: str, title: str) -> str:
    key = normalize_title(title) or url
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def _entry_date(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        value = entry.get(attr)
        if value:
            try:
                return datetime.fromtimestamp(calendar.timegm(value), tz=timezone.utc)
            except (OverflowError, ValueError, TypeError):
                continue
    return None


def parse_feed(content: bytes, source: str, lang: str, country: str = "") -> list[Article]:
    feed = feedparser.parse(content)
    now = datetime.now(timezone.utc)
    articles = []
    for entry in feed.entries:
        title = clean_text(entry.get("title", ""), 250)
        url = entry.get("link", "")
        if not title or not url:
            continue
        published = _entry_date(entry) or now
        summary = clean_text(entry.get("summary", "") or entry.get("description", ""))
        if normalize_title(summary).startswith(normalize_title(title)[:40]):
            summary = ""  # Google News répète le titre dans le résumé
        articles.append(
            Article(
                id=article_id(url, title),
                title=title,
                summary=summary,
                url=url,
                source=source,
                lang=lang,
                published=published.isoformat(timespec="seconds"),
                country=country,
            )
        )
    return articles


def parse_gdelt(payload: dict) -> list[Article]:
    articles = []
    for item in payload.get("articles", []) or []:
        title = clean_text(item.get("title", ""), 250)
        url = item.get("url", "")
        if not title or not url:
            continue
        try:
            published = datetime.strptime(item.get("seendate", ""), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            published = datetime.now(timezone.utc)
        articles.append(
            Article(
                id=article_id(url, title),
                title=title,
                summary="",
                url=url,
                source=f"GDELT · {item.get('domain', '?')}",
                lang=(item.get("language") or "?")[:20],
                published=published.isoformat(timespec="seconds"),
                country=item.get("sourcecountry", "") or "",
            )
        )
    return articles


def build_feed_list(sources: dict) -> list[dict]:
    feeds = [dict(f) for f in sources.get("rss", [])]
    for ed in sources.get("google_news_editions", []):
        feeds.append(
            {
                "name": f"Google News {ed['gl']}",
                "url": f"https://news.google.com/rss?hl={ed['hl']}&gl={ed['gl']}&ceid={ed['ceid']}",
                "lang": ed["hl"],
                "country": ed["gl"],
            }
        )
    for s in sources.get("google_news_searches", []):
        feeds.append(
            {
                "name": f"Google News recherche {s['gl']}",
                "url": (
                    f"https://news.google.com/rss/search?q={quote_plus(s['q'])}"
                    f"&hl={s['hl']}&gl={s['gl']}&ceid={s['ceid']}"
                ),
                "lang": s["hl"],
                "country": s["gl"],
            }
        )
    return feeds


def _fetch(session: requests.Session, url: str, timeout: float) -> bytes | None:
    try:
        resp = session.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.content
    except requests.RequestException as exc:
        log.warning("Source injoignable %s : %s", url[:90], exc)
        return None


def fetch_rss(feeds: list[dict], timeout: float) -> tuple[list[Article], int]:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    def work(feed: dict) -> list[Article] | None:
        content = _fetch(session, feed["url"], timeout)
        if content is None:
            return None
        return parse_feed(content, feed["name"], feed.get("lang", "?"), feed.get("country", ""))

    articles: list[Article] = []
    failures = 0
    with ThreadPoolExecutor(max_workers=12) as pool:
        for result in pool.map(work, feeds):
            if result is None:
                failures += 1
            else:
                articles.extend(result)
    return articles, failures


def fetch_gdelt(queries: list[str], timeout: float) -> tuple[list[Article], int]:
    """GDELT indexe la presse mondiale dans plus de 60 langues. Limite : 1 requête / 5 s."""
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    articles: list[Article] = []
    failures = 0
    for i, query in enumerate(queries):
        if i:
            time.sleep(6)
        url = (
            "https://api.gdeltproject.org/api/v2/doc/doc?mode=artlist&format=json"
            f"&maxrecords=150&timespan=3h&sort=hybridrel&query={quote_plus(query)}"
        )
        content = _fetch(session, url, timeout)
        if content is None:
            failures += 1
            continue
        try:
            articles.extend(parse_gdelt(json.loads(content)))
        except (json.JSONDecodeError, AttributeError):
            log.warning("Réponse GDELT illisible pour %s", query)
            failures += 1
    return articles, failures


def collect_all(sources: dict, timeout: float) -> tuple[list[Article], dict]:
    feeds = build_feed_list(sources)
    rss_articles, rss_fail = fetch_rss(feeds, timeout)
    gdelt_articles, gdelt_fail = fetch_gdelt(sources.get("gdelt_queries", []), timeout)
    report = {
        "sources_total": len(feeds) + len(sources.get("gdelt_queries", [])),
        "sources_en_echec": rss_fail + gdelt_fail,
    }
    return rss_articles + gdelt_articles, report


def filter_recent(articles: list[Article], max_age_hours: int) -> list[Article]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    return [a for a in articles if datetime.fromisoformat(a.published) >= cutoff]
