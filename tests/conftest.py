import pytest


@pytest.fixture(autouse=True)
def clear_provider_failure_cache():
    from backend.services.metadata_providers import clear_provider_failure_cache

    clear_provider_failure_cache()


@pytest.fixture(autouse=True)
def clear_auth_cache():
    from backend.auth.dependencies import clear_auth_cache

    clear_auth_cache()


@pytest.fixture(autouse=True)
def block_recommendation_broad_external_exploration(monkeypatch, request):
    path = str(request.node.path)
    if not (
        path.endswith("test_api.py")
        or "test_recommendation" in path
    ):
        return

    from backend.services.external_candidate_exploration import ExternalExplorationDiagnostics

    monkeypatch.setattr(
        "backend.services.recommendation_discovery.explore_external_candidates",
        lambda *_args, **_kwargs: ([], ExternalExplorationDiagnostics()),
    )
