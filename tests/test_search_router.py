"""验证检索路由的确定性规则及参数边界。"""

import pytest

from app.services.search_router import (
    SearchRequest,
    SearchRouter,
)


@pytest.fixture
def router():
    return SearchRouter()


def test_document_id_only_routes_to_metadata(router):
    plan = router.select(SearchRequest(document_id=31))

    assert plan.retrievers == ("metadata",)
    assert plan.reason == "document_id_lookup"
    assert plan.planner == "rule_based"


def test_title_routes_to_metadata(router):
    plan = router.select(
        SearchRequest(title="Audio Deepfake Detection")
    )

    assert plan.retrievers == ("metadata",)


def test_chinese_query_routes_to_literal(router):
    plan = router.select(
        SearchRequest(query="音频深度伪造检测")
    )

    assert plan.retrievers == ("keyword_literal",)


def test_english_query_routes_to_fts(router):
    plan = router.select(
        SearchRequest(query="spectrogram detection")
    )

    assert plan.retrievers == ("keyword_fts",)


def test_document_id_with_query_keeps_keyword_route(router):
    plan = router.select(
        SearchRequest(
            query="spectrogram",
            document_id=31,
        )
    )

    assert plan.retrievers == ("keyword_fts",)


def test_explicit_literal_overrides_auto(router):
    plan = router.select(
        SearchRequest(
            query="spectrogram",
            strategy="literal",
        )
    )

    assert plan.retrievers == ("keyword_literal",)


def test_explicit_metadata_requires_filter(router):
    with pytest.raises(ValueError):
        router.select(
            SearchRequest(
                query="spectrogram",
                strategy="metadata",
            )
        )


def test_empty_auto_request_rejected(router):
    with pytest.raises(ValueError):
        router.select(SearchRequest())


def test_invalid_limit_rejected(router):
    with pytest.raises(ValueError):
        router.select(
            SearchRequest(query="audio", limit=0)
        )