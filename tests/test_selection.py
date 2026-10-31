from datetime import datetime, timezone

from fab.collect import Article, article_id
from fab.selection import cluster_articles, select_for_analysis


def art(title, source):
    return Article(article_id(source + title, title + source), title, "", f"https://{source}/{len(title)}", source, "en",
                   datetime.now(timezone.utc).isoformat())


def test_similar_titles_are_clustered():
    arts = [art("PixNest photo service to shut down in December", "A"),
            art("PixNest photo service will shut down in December", "B"),
            art("Football team wins the regional cup", "C")]
    clusters = cluster_articles(arts)
    assert sorted(len(c.articles) for c in clusters) == [1, 2]


WORDS = ["apple", "banana", "cherry", "durian", "elder", "fig", "grape", "kiwi", "lemon", "mango", "nectarine", "olive"]


def test_selection_prioritises_multi_source_triggers_and_caps():
    arts = [art("Fuel shortage hits the whole country", s) for s in "ABC"] + [art(f"{w} market report", "D") for w in WORDS]
    items = select_for_analysis(arts, max_items=10, max_per_source=5)
    assert len(items) == 6  # 1 sujet multi-sources + 5 max pour la source D
    assert items[0]["titre"].startswith("Fuel shortage") and items[0]["nb_medias"] == 3
    assert [i["ref"] for i in items][:2] == ["A1", "A2"]
