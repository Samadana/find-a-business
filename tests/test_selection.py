from datetime import datetime, timezone

from fab.collect import Article, article_id
from fab.selection import cluster_articles, merge_triage, select_for_analysis, split_batches


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


def test_merge_triage_keeps_safety_net_and_caps():
    cands = [{"ref": f"A{i}"} for i in range(1, 21)]
    out = merge_triage(cands, ["A20", "A3", "A99", "A19"], always_keep=3, max_items=5)
    assert [c["ref"] for c in out] == ["A1", "A2", "A3", "A20", "A19"]


def test_interleave_regions_alternates():
    from fab.selection import interleave_regions
    items = [("europe", 1), ("europe", 2), ("europe", 3), ("asie", 4), ("afrique", 5)]
    out = interleave_regions(items, lambda x: x[0])
    assert [x[1] for x in out] == [1, 4, 5, 2, 3]


def test_merge_triage_caps_dominant_region():
    from fab.selection import merge_triage
    cands = [{"ref": f"E{i}", "region": "europe"} for i in range(10)] + [{"ref": f"A{i}", "region": "asie"} for i in range(3)]
    refs = [c["ref"] for c in cands]
    out = merge_triage(cands, refs, always_keep=0, max_items=6, max_share=0.5)
    regions = [c["region"] for c in out]
    assert regions.count("europe") == 3 and regions.count("asie") == 3


def test_trigger_hits_non_latin():
    from fab.selection import trigger_hits
    assert trigger_hits(set(), "半導体の品薄が続く") == 1
    assert trigger_hits({"shortage"}, "chip shortage") == 1


def test_region_of():
    from fab.regions import region_of
    assert region_of("NG") == "afrique" and region_of("South Korea") == "asie"
    assert region_of("", "pt-BR") == "amerique-latine" and region_of("", "en", "business") == "business"


def test_split_batches_mixes_regions_without_loss():
    regions = [f"r{k}" for k in range(9)]
    # Groupés par région comme après un tri par priorité : chaque région a 9 sujets.
    items = [{"ref": f"A{r}{k}", "region": r} for r in regions for k in range(9)]
    batches = split_batches(items, 3)
    assert [len(b) for b in batches] == [27, 27, 27]
    refs = [it["ref"] for b in batches for it in b]
    assert sorted(refs) == sorted(it["ref"] for it in items) and len(set(refs)) == len(refs)
    for b in batches:
        assert {it["region"] for it in b} == set(regions)
    # Taille maximale = arrondi supérieur de total / lots ; lots vides retirés ; au moins un lot.
    assert [len(b) for b in split_batches(items[:10], 3)] == [4, 3, 3]
    assert len(split_batches(items[:2], 5)) == 2 and len(split_batches(items, 0)) == 1
