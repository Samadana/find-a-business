from fab import corroborate as c


def test_corroborate_adds_distinct_outlets(monkeypatch):
    found = [
        {"titre": "a", "url": "u1", "source": "BBC", "langue": "en", "date": "d"},
        {"titre": "b", "url": "u2", "source": "Reuters", "langue": "en", "date": "d"},
        {"titre": "c", "url": "u3", "source": "Reuters", "langue": "en", "date": "d"},
        {"titre": "d", "url": "u4", "source": "AP", "langue": "en", "date": "d"},
    ]
    monkeypatch.setattr(c, "search_google_news", lambda session, q, timeout: found)
    idea = {"requete_verification": "Binance hack", "sources": [{"url": "u0", "source": "GDELT · bbc.com"}, {"url": "x", "source": "BBC"}]}
    assert c.corroborate([idea], 5) == 2
    assert [s["source"] for s in idea["sources"][2:]] == ["Reuters", "AP"] and idea["sources_confirmation"] == 2


def test_corroborate_skips_without_query(monkeypatch):
    monkeypatch.setattr(c, "search_google_news", lambda *a: (_ for _ in ()).throw(AssertionError("ne doit pas chercher")))
    assert c.corroborate([{"sources": []}], 5) == 0
