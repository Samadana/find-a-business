from datetime import datetime, timedelta, timezone

from fab.collect import Article, build_feed_list, filter_recent, normalize_title, parse_feed, parse_gdelt

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>T</title>
<item><title>PixNest va fermer - Le Monde</title><link>https://ex.com/1</link>
<description>&lt;p&gt;Le service &lt;b&gt;ferme&lt;/b&gt;.&lt;/p&gt;</description>
<pubDate>Sat, 31 Oct 2026 10:00:00 GMT</pubDate></item>
<item><title></title><link>https://ex.com/2</link></item>
</channel></rss>"""


def test_parse_feed_cleans_html_and_skips_empty():
    arts = parse_feed(RSS, "Src", "fr", "FR")
    assert len(arts) == 1
    a = arts[0]
    assert a.summary == "Le service ferme ."
    assert a.published.startswith("2026-10-31T10:00:00")
    assert a.country == "FR"


def test_normalize_title_strips_outlet_and_accents():
    assert normalize_title("Pénurie d'essence ! - Le Figaro") == "penurie d essence"


def test_parse_gdelt():
    arts = parse_gdelt({"articles": [{"title": "Escasez", "url": "https://x.es", "seendate": "20261031T100000Z",
                                      "domain": "x.es", "language": "Spanish", "sourcecountry": "Spain"}]})
    assert arts[0].lang == "Spanish" and arts[0].source == "GDELT · x.es"


def test_build_feed_list_includes_google_news():
    feeds = build_feed_list({"rss": [{"name": "a", "url": "u", "lang": "en"}],
                             "google_news_editions": [{"hl": "fr", "gl": "FR", "ceid": "FR:fr"}],
                             "google_news_searches": [{"q": "a b", "hl": "fr", "gl": "FR", "ceid": "FR:fr"}]})
    assert len(feeds) == 3 and "q=a+b" in feeds[2]["url"]


def test_filter_recent():
    now = datetime.now(timezone.utc)
    old = Article("1", "t", "", "u", "s", "en", (now - timedelta(hours=50)).isoformat())
    new = Article("2", "t", "", "u", "s", "en", now.isoformat())
    assert filter_recent([old, new], 36) == [new]
