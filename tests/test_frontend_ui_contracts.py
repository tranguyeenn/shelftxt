from pathlib import Path


FRONTEND = Path(__file__).resolve().parents[1] / "frontend" / "src"


def test_language_is_not_rendered_in_normal_book_ui_flows():
    user_flow_files = [
        FRONTEND / "pages" / "BookDetailPage.tsx",
        FRONTEND / "components" / "books" / "BookEditModal.tsx",
        FRONTEND / "components" / "books" / "BookCard.tsx",
        FRONTEND / "components" / "books" / "BookLibraryCard.tsx",
        FRONTEND / "features" / "recommendations" / "RecommendationCard.tsx",
    ]

    for path in user_flow_files:
        assert "language" not in path.read_text().casefold(), path


def test_edit_book_modal_is_mobile_scrollable():
    source = (
        FRONTEND / "components" / "books" / "BookEditModal.tsx"
    ).read_text()

    assert "overflow-y-auto" in source
    assert "max-h-[calc(100dvh-1rem)]" in source
    assert "sm:max-h-[calc(100dvh-2rem)]" in source
    assert "[-webkit-overflow-scrolling:touch]" in source


def test_stats_page_replaces_reading_moods_with_reading_insights():
    source = (FRONTEND / "pages" / "InsightsPage.tsx").read_text()

    assert "No reading mood data yet" not in source
    assert "Reading Insights" in source
    assert "fetchReadingInsights" in source
