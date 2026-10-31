from fab.report import build_standalone_dashboard


def test_standalone_dashboard_embeds_data_safely():
    html = build_standalone_dashboard([{"titre": "x</script><b>"}], [], {"historique": []}).decode()
    assert "window.FAB_DATA" in html
    assert "x</script><b>" not in html and "x<\\/script>" in html
