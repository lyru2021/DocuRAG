"""验证 DOI 和标题参数能够贯通检索路由与执行编排。"""

from unittest.mock import Mock

import pytest

from app.schemas.search import SearchResult
from app.services.retrievers import KeywordRetriever, MetadataRetriever
from app.services.search_orchestrator import SearchOrchestrator
from app.services.search_router import SearchRequest, SearchRouter


def test_doi_routes_to_metadata():
    """DOI 应优先走元数据路径。"""

    plan = SearchRouter().select(
        SearchRequest(doi="10.1234/example")
    )

    assert plan.retrievers == ("metadata",)
    assert plan.reason == "explicit_doi_filter"


def test_title_is_forwarded_through_orchestrator():
    """标题过滤条件应真实到达元数据检索器。"""

    service = Mock()
    service.search_papers.return_value = []

    orchestrator = SearchOrchestrator({
        "metadata": MetadataRetriever(service),
    })

    response = orchestrator.execute(
        SearchRequest(title="Audio Deepfake Detection")
    )

    assert response.execution_log[0].status == "success"

    service.search_papers.assert_called_once_with(
        document_id=None,
        title="Audio Deepfake Detection",
        doi=None,
        limit=20,
    )


def test_doi_is_forwarded_through_orchestrator():
    """DOI 必须真实传入 SearchService。"""

    service = Mock()
    service.search_papers.return_value = [
        SearchResult(
            document_id=31,
            title="Audio Deepfake Detection",
            retrieval_source="metadata",
        )
    ]

    orchestrator = SearchOrchestrator({
        "metadata": MetadataRetriever(service),
    })

    response = orchestrator.execute(
        SearchRequest(doi="10.1234/example")
    )

    assert len(response.results) == 1
    assert response.execution_log[0].status == "success"

    service.search_papers.assert_called_once_with(
        document_id=None,
        title=None,
        doi="10.1234/example",
        limit=20,
    )


def test_unmatched_doi_returns_empty_results():
    """没有 DOI 命中时不得制造候选记录。"""

    service = Mock()
    service.search_papers.return_value = []

    orchestrator = SearchOrchestrator({
        "metadata": MetadataRetriever(service),
    })

    response = orchestrator.execute(
        SearchRequest(doi="10.9999/not-found")
    )

    assert response.results == []
    assert response.execution_log[0].status == "success"
    assert response.execution_log[0].result_count == 0


def test_keyword_rejects_structured_doi_filter():
    """关键词工具不得静默丢弃 DOI 条件。"""

    service = Mock()

    with pytest.raises(ValueError):
        KeywordRetriever(service).retrieve(
            "spectrogram",
            doi="10.1234/example",
        )

    service.search_chunks.assert_not_called()