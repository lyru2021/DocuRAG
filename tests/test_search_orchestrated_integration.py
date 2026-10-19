"""使用真实 PostgreSQL 验证多策略 HTTP 检索及证据来源。"""

import pytest

from app.models.document import Chunk, Document
from app.models.paper import PaperMetadata


@pytest.fixture
def searchable_paper(db_session):
    """创建包含真实页码和英文专业术语的已解析论文。"""

    content = (
        "Dynamic graph neural networks detect fraud "
        "using temporal relationships."
    )

    document = Document(
        title="Graph Fraud Detection",
        filename="graph_fraud.pdf",
        parse_status="parsed",
        extracted_text=content,
        text_length=len(content),
    )

    db_session.add(document)
    db_session.flush()

    chunk = Chunk(
        document_id=document.id,
        chunk_index=0,
        content=content,
        start_char=0,
        end_char=len(content),
        page_start=2,
        page_end=2,
    )

    db_session.add(chunk)
    db_session.commit()

    return document, chunk


def test_hybrid_search_returns_real_fused_evidence(
    client,
    searchable_paper,
):
    """Hybrid 应真实执行 Literal 和 FTS，并合并同一 Chunk。"""

    document, chunk = searchable_paper

    response = client.post(
        "/search/orchestrated",
        json={
            "query": "graph",
            "document_id": document.id,
            "strategy": "hybrid",
            "limit": 5,
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["planner"] == "rule_based"
    assert body["selected_retrievers"] == [
        "keyword_literal",
        "keyword_fts",
    ]
    assert body["fusion_method"] == "rrf"

    assert [
        item["status"]
        for item in body["execution_log"]
    ] == ["success", "success"]

    assert len(body["results"]) == 1

    hit = body["results"][0]

    assert hit["document_id"] == document.id
    assert hit["chunk_id"] == chunk.id
    assert hit["title"] == document.title
    assert hit["content"] == chunk.content
    assert hit["page_start"] == 2
    assert hit["page_end"] == 2

    # 两个 Retriever 都命中同一个 Chunk，RRF 累加排名分。
    assert hit["score"] == pytest.approx(
        1 / 61 + 1 / 61
    )

    key = f"chunk:{document.id}:{chunk.id}"

    assert body["candidate_sources"][key] == [
        "keyword_literal",
        "keyword_fts",
    ]


def test_literal_search_preserves_real_evidence(
    client,
    db_session,
):
    """中文 Literal 应返回真实 Chunk 和原始页码。"""

    content = "高温超导磁体的失超保护需要及时检测。"

    document = Document(
        title="超导磁体研究",
        filename="magnet.pdf",
        parse_status="parsed",
    )

    db_session.add(document)
    db_session.flush()

    chunk = Chunk(
        document_id=document.id,
        chunk_index=0,
        content=content,
        start_char=0,
        end_char=len(content),
        page_start=3,
        page_end=3,
    )

    db_session.add(chunk)
    db_session.commit()

    response = client.post(
        "/search/orchestrated",
        json={
            "query": "失超保护",
            "document_id": document.id,
            "strategy": "literal",
            "limit": 5,
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["selected_retrievers"] == [
        "keyword_literal"
    ]
    assert body["fusion_method"] is None
    assert body["execution_log"][0]["status"] == "success"
    assert len(body["results"]) == 1

    hit = body["results"][0]

    assert hit["document_id"] == document.id
    assert hit["chunk_id"] == chunk.id
    assert hit["content"] == content
    assert hit["page_start"] == 3
    assert hit["page_end"] == 3
    assert hit["retrieval_source"] == "postgres_literal"

    key = f"chunk:{document.id}:{chunk.id}"
    assert body["candidate_sources"][key] == [
        "keyword_literal"
    ]


def test_doi_search_matches_real_paper_metadata(
    client,
    db_session,
):
    """通过 PaperMetadata 的真实外键执行 DOI 精确匹配。"""

    document = Document(
        title="DOI Verification Paper",
        filename="doi_paper.pdf",
        parse_status="metadata_only",
    )

    db_session.add(document)
    db_session.flush()

    metadata = PaperMetadata(
        document_id=document.id,
        paper_title=document.title,
        doi="10.1234/docurag-test",
        metadata_status="verified",
    )

    db_session.add(metadata)
    db_session.commit()

    response = client.post(
        "/search/orchestrated",
        json={
            "doi": "10.1234/DOCURAG-TEST",
            "strategy": "auto",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["selected_retrievers"] == ["metadata"]
    assert body["execution_log"][0]["status"] == "success"

    matching = [
        item
        for item in body["results"]
        if item["document_id"] == document.id
    ]

    assert len(matching) == 1
    assert matching[0]["retrieval_source"] == "metadata"


def test_hybrid_no_match_is_success(
    client,
    searchable_paper,
):
    """没有关键词命中时，应与检索器失败区别开。"""

    document, _ = searchable_paper

    response = client.post(
        "/search/orchestrated",
        json={
            "query": "uniquenoresulttoken987654",
            "document_id": document.id,
            "strategy": "hybrid",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["results"] == []
    assert body["candidate_sources"] == {}

    assert [
        log["status"]
        for log in body["execution_log"]
    ] == ["success", "success"]

    assert all(
        log["result_count"] == 0
        for log in body["execution_log"]
    )


def test_legacy_search_api_still_works(
    client,
    searchable_paper,
):
    """新增编排接口不得破坏已有正文检索 API。"""

    document, chunk = searchable_paper

    response = client.post(
        "/search",
        json={
            "query": "graph",
            "mode": "literal",
            "document_id": document.id,
        },
    )

    assert response.status_code == 200

    hits = response.json()

    assert len(hits) == 1
    assert hits[0]["document_id"] == document.id
    assert hits[0]["chunk_id"] == chunk.id
    assert hits[0]["content"] == chunk.content
