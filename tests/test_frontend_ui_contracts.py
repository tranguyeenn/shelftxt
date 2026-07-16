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


def test_ranking_page_renders_external_recommendations_without_book_id_requirement():
    source = (FRONTEND / "pages" / "RankingPage.tsx").read_text()

    assert 'visibleSections.every((section) => section.items.length === 0)' in source
    assert 'item.library_state.in_library ? "Start reading" : "Add to library"' in source
    assert "book_id: inLibrary ?" in source
    assert "library_state.in_library" in source


def test_frontend_uses_explicit_mixed_recommendation_types():
    source = (FRONTEND / "lib" / "types.ts").read_text()

    assert 'export type RecommendationSource = "library" | "external";' in source
    assert "export type RecommendationBookRef" in source
    assert "id?: string | null" in source
    assert "book_id?: number | string | null" in source
    assert "source?: RecommendationSource" in source
    assert "is_in_library?: boolean" in source
    assert "provider?: string | null" in source


def test_external_recommendation_with_null_book_id_can_render_and_use_placeholder():
    ranking_page = (FRONTEND / "pages" / "RankingPage.tsx").read_text()
    book_cover = (FRONTEND / "components" / "ui" / "BookCover.tsx").read_text()

    assert "book_id: inLibrary ? String" in ranking_page
    assert "book.id ?? recommendationTitleAuthorIdentity" in ranking_page
    assert 'item.library_state.in_library ? "On your shelf" : "Outside your library"' in ranking_page
    assert 'item.library_state.in_library ? "Start reading" : "Add to library"' in ranking_page
    assert "selected_edition_id: inLibrary ? book.id ?? null : null" in ranking_page
    assert "BookCoverPlaceholder" in book_cover
    assert "if (!coverUrl || failed)" in book_cover


def test_mixed_external_items_do_not_dedupe_on_null_book_id():
    ranking_page = (FRONTEND / "pages" / "RankingPage.tsx").read_text()
    feedback_helper = (FRONTEND / "lib" / "recommendationFeedback.ts").read_text()

    assert "const key = visibleRecommendationKey(item)" in ranking_page
    assert "?? book.id" in feedback_helper
    assert "?? recommendationTitleAuthorIdentity(book.title, book.author)" in feedback_helper


def test_recommendation_page_has_no_development_diagnostics_ui():
    source = (FRONTEND / "pages" / "RankingPage.tsx").read_text()

    assert "recommendationSectionDiagnostics" not in source
    assert "visibleRecommendationCardRows" not in source
    assert "API returned" not in source
    assert "Unique visible cards" not in source
    assert "Library visible" not in source
    assert "External visible" not in source
    assert 'data-testid="visible-recommendation-cards"' not in source
    assert 'data-testid="recommendation-diagnostics"' not in source
    assert "import.meta.env.DEV" not in source


def test_discover_visible_cards_are_globally_deduplicated_and_counted_once():
    source = (FRONTEND / "pages" / "RankingPage.tsx").read_text()

    assert "export function visibleRecommendationSections" in source
    assert ".filter((section) => section.items.length > 0)" in source
    assert "item.canonical_identity" in source
    assert "?? item.recommendation_id" in source
    assert "?? item.work_id" in source
    assert "item.book_id" not in source[source.index("function visibleRecommendationKey"):source.index("function sectionItemSource")]


def test_discover_external_cards_are_visibly_external_and_addable():
    source = (FRONTEND / "pages" / "RankingPage.tsx").read_text()

    assert "Outside your library" in source
    assert "Add to library" in source
    assert "Start reading" in source
    assert 'source === "external" ? true : item.external_discovery' in source
    assert 'item.source === "external"' in source
    assert 'item.source === "library"' in source
    assert "? `/app/book/${encodeURIComponent(item.book_id ?? item.work_id)}`" in source
    assert ': "/app/add"' in source
    assert "progress" not in source[source.index("function StructuredRecommendationCard"):]


def test_external_item_source_cannot_be_overwritten_by_nested_book_data():
    source = (FRONTEND / "pages" / "RankingPage.tsx").read_text()
    replacement_mapper = source[source.index("function sectionItemFromRecommendation"):source.index("function dedupeSectionItems")]

    assert "const inLibrary = recommendationInLibrary(item)" in replacement_mapper
    assert "const source = recommendationSource(item)" in replacement_mapper
    assert 'item.source === "external"' in source
    assert 'item.source_type === "external_discovery"' in source
    assert "item.external_discovery === true" in source
    assert "book.book_id" in replacement_mapper
    assert "recommendationSource(item)" in source[source.index("function recommendationInLibrary"):]


def test_mixed_library_external_rendering_keeps_user_facing_contract():
    source = (FRONTEND / "pages" / "RankingPage.tsx").read_text()

    assert "visibleSections.map((section)" in source
    assert "<StructuredRecommendationCard key={visibleRecommendationKey(item)}" in source
    assert "recommendationActionLabel(item)" in source
    assert "recommendationBadgeLabel(item)" in source
    assert "Outside your library" in source
    assert "Add to library" in source
    assert "On your shelf" in source


def test_discover_fetches_clustered_recommendations_before_sections_fallback():
    source = (FRONTEND / "pages" / "RankingPage.tsx").read_text()

    assert 'fetchJson<RecommendationClustersResponse>' in source
    assert 'recommendationClustersQuery(settings)' in source
    assert "/recommendations/clusters?" in source
    assert "normalizeRecommendationClusterSections(clustered)" in source
    assert "if (clusterSections.length > 0)" in source
    assert "loadFallbackSections(refresh, excludeIds, filters)" in source
    assert "recommendationSectionsQuery(settings, refresh, excludeIds, filters)" in source


def test_discover_cluster_sections_render_titles_anchors_themes_and_cards():
    source = (FRONTEND / "pages" / "RankingPage.tsx").read_text()

    assert "function normalizeRecommendationClusterSections" in source
    assert "function clusterSectionFromCluster" in source
    assert 'type: "cluster"' in source
    assert "title: cluster.title" in source
    assert "anchors: Array.isArray(cluster.anchors) ? cluster.anchors : []" in source
    assert "dominant_genres: Array.isArray(cluster.dominant_genres)" in source
    assert "dominant_themes: Array.isArray(cluster.dominant_themes)" in source
    assert "cluster.recommendations.map((item) =>" in source
    assert "cluster_id: cluster.cluster_id" in source
    assert "Anchors:" in source
    assert "section.dominant_themes" in source
    assert "section.dominant_genres" in source
    assert "<StructuredRecommendationCard key={visibleRecommendationKey(item)}" in source


def test_discover_cluster_response_types_are_explicit():
    source = (FRONTEND / "lib" / "types.ts").read_text()

    assert "export type AnchorBook" in source
    assert "export type RecommendationCluster" in source
    assert "cluster_id: string" in source
    assert "anchors: AnchorBook[]" in source
    assert "dominant_genres: string[]" in source
    assert "dominant_themes: string[]" in source
    assert "cluster_size: number" in source
    assert "recommendations: RecommendationSectionItem[]" in source
    assert "export type RecommendationClustersResponse = RecommendationCluster[]" in source


def test_clustered_discover_preserves_external_cards_and_global_dedupe():
    source = (FRONTEND / "pages" / "RankingPage.tsx").read_text()

    assert "normalizeRecommendationClusterSections(clustered)" in source
    assert "visibleRecommendationSections(sections)" in source
    assert "const seen = new Set<string>()" in source
    assert "item.canonical_identity" in source
    assert "?? item.recommendation_id" in source
    assert "?? item.work_id" in source
    assert 'item.library_state.in_library ? "Start reading" : "Add to library"' in source
    assert 'item.library_state.in_library ? "On your shelf" : "Outside your library"' in source
    assert "BookCover" in source


def test_cluster_fixture_titles_are_covered_by_end_to_end_cluster_tests():
    source = (FRONTEND / "pages" / "RankingPage.tsx").read_text()
    backend_cluster_tests = (Path(__file__).resolve().parents[1] / "tests" / "test_recommendation_clusters.py").read_text()

    assert "cluster.recommendations.map((item) =>" in source
    assert "Killer Instinct" in backend_cluster_tests
    assert "ya-mystery-thriller" in backend_cluster_tests
    assert "Happy Place" in backend_cluster_tests
    assert "contemporary-romance-new-adult" in backend_cluster_tests


def test_happy_place_trace_output_is_removed_from_discover_page():
    source = (FRONTEND / "pages" / "RankingPage.tsx").read_text()

    assert "traceHappyPlaceRecommendation" not in source
    assert "Happy Place recommendation trace" not in source
    assert 'stage: "raw API item"' not in source
    assert 'stage: "section response"' not in source
    assert 'stage: "frontend parsed item"' not in source
    assert 'stage: "deduplicated item"' not in source
    assert 'stage: "data passed to RecommendationCard"' not in source
    assert 'stage: "rendered action and badge"' not in source


def test_recommendation_cards_expose_not_interested_feedback():
    recommendation_card = (FRONTEND / "features" / "recommendations" / "RecommendationCard.tsx").read_text()
    recommendation_list = (FRONTEND / "features" / "recommendations" / "RecommendationsList.tsx").read_text()
    ranking_page = (FRONTEND / "pages" / "RankingPage.tsx").read_text()
    dashboard_page = (FRONTEND / "pages" / "DashboardPage.tsx").read_text()
    feedback_helper = (FRONTEND / "lib" / "recommendationFeedback.ts").read_text()

    assert "Not interested" in recommendation_card
    assert "aria-label={`Not interested in" in recommendation_card
    assert "submitRecommendationFeedback" in recommendation_list
    assert "Got it. We replaced that recommendation." in recommendation_list
    assert "submitSectionRecommendationFeedback" in ranking_page
    assert "setSections(previousSections)" in ranking_page
    assert "submitRecommendationFeedback" in dashboard_page
    assert '"/recommendations/feedback"' in feedback_helper
    assert "current_recommendation_ids" in feedback_helper
    assert "replacement" in feedback_helper
    assert "title_author:" in feedback_helper
    assert "normalizeIdentityPart" in feedback_helper


def test_not_interested_feedback_persists_identity_context_and_refetches_discover():
    ranking_page = (FRONTEND / "pages" / "RankingPage.tsx").read_text()
    feedback_helper = (FRONTEND / "lib" / "recommendationFeedback.ts").read_text()
    api_helper = (FRONTEND / "lib" / "api.ts").read_text()

    assert "canonical_identity" in feedback_helper
    assert "action: feedbackType" in feedback_helper
    assert "source:" in feedback_helper
    assert "cluster_id: item.cluster_id" in feedback_helper
    assert "clearApiClientCache()" in api_helper
    assert "MUTATING_METHODS.has(method)" in api_helper
    assert "await load(true, currentIds, appliedFilters)" in ranking_page
    assert "setSections(previousSections)" in ranking_page
    assert "Failed to update recommendations" in ranking_page
