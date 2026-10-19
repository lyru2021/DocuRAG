"""验证统一 Retriever 协议及已有检索服务适配。"""

from unittest.mock import Mock

import pytest

from app.services.retrievers import (
    KeywordRetriever,
    MetadataRetriever,
    Retriever,
)


def test_keyword_retriever_delegates_to_service():
    """关键词检索器应复用现有 Chunk 检索。"""

    service = Mock()
    service.search_chunks.return_value = []

    retriever = KeywordRetriever(service, mode="fts")

    assert isinstance(retriever, Retriever)
    assert retriever.retrieve(
        "graph neural networks",
        document_id=31,
        limit=5,
    ) == []

    service.search_chunks.assert_called_once_with(
        "graph neural networks",
        mode="fts",
        document_id=31,
        limit=5,
    )


def test_metadata_retriever_by_document_id():
    """指定文档 ID 时应执行精确元数据查询。"""

    service = Mock()
    service.search_papers.return_value = []

    retriever = MetadataRetriever(service)

    assert isinstance(retriever, Retriever)
    retriever.retrieve("", document_id=31, limit=5)

    service.search_papers.assert_called_once_with(
        document_id=31,
        limit=5,
    )


def test_metadata_retriever_by_title():
    """未提供 ID 时，应按标题检索。"""

    service = Mock()
    service.search_papers.return_value = []

    retriever = MetadataRetriever(service)
    retriever.retrieve("Deepfake Detection", limit=10)

    service.search_papers.assert_called_once_with(
        title="Deepfake Detection",
        limit=10,
    )


def test_keyword_retriever_rejects_unknown_mode():
    """不支持的模式不能静默回退。"""

    with pytest.raises(ValueError):
        KeywordRetriever(Mock(), mode="vector")