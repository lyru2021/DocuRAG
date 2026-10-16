"""验证论文元数据和正文检索 HTTP API。"""

from app.models.document import Chunk, Document


def test_paper_search_api(client, db_session):
    """元数据 API 返回真实论文信息。"""

    document = Document(
        title="Dynamic Graph Fraud Detection",
        filename="dynamic-graph.pdf",
        authors="Alice Chen",
        publication_year=2025,
    )
    db_session.add(document)
    db_session.commit()

    response = client.get(
        "/papers/search",
        params={
            "document_id": document.id,
            "author": "Alice",
            "year": 2025,
        },
    )
    print("STATUS:", response.status_code)
    print("BODY:", response.json())

    assert response.status_code == 200
    data = response.json()

    assert len(data) == 1
    assert data[0]["document_id"] == document.id
    assert data[0]["retrieval_source"] == "metadata"


def test_chunk_search_api(client, db_session):
    """正文检索 API 返回真实 Chunk 证据和页码。"""

    document = Document(
        title="HTS Quench Protection",
        filename="hts-search.pdf",
        parse_status="parsed",
    )
    db_session.add(document)
    db_session.flush()

    chunk = Chunk(
        document_id=document.id,
        chunk_index=0,
        content="光纤传感器可用于监测超导磁体的温度变化。",
        page_start=6,
        page_end=6,
    )
    db_session.add(chunk)
    db_session.commit()

    response = client.post(
        "/search",
        json={
            "query": "光纤传感器",
            "mode": "literal",
            "document_id": document.id,
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert len(data) == 1
    assert data[0]["chunk_id"] == chunk.id
    assert data[0]["page_start"] == 6
    assert "光纤传感器" in data[0]["content"]


def test_search_api_rejects_invalid_mode(client):
    """不允许未知检索模式。"""

    response = client.post(
        "/search",
        json={
            "query": "neural networks",
            "mode": "unknown",
        },
    )

    assert response.status_code == 422


def test_search_api_rejects_empty_query(client):
    """空查询不得执行全文扫描。"""

    response = client.post(
        "/search",
        json={"query": ""},
    )

    assert response.status_code == 422


def test_paper_search_route_priority():
    """静态搜索路由应优先于动态论文详情路由。"""

    from app.main import app

    routes = [
        (route.path, getattr(route, "methods", set()))
        for route in app.routes
    ]

    search_index = next(
        i for i, (path, methods) in enumerate(routes)
        if path == "/papers/search" and "GET" in methods
    )

    detail_index = next(
        i for i, (path, methods) in enumerate(routes)
        if path == "/papers/{document_id}" and "GET" in methods
    )

    assert search_index < detail_index