"""验证多策略检索 API 的请求校验、路由和响应结构。"""

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_orchestrated_api_rejects_empty_request():
    """空请求应被参数验证拒绝。"""

    response = client.post(
        "/search/orchestrated",
        json={},
    )

    assert response.status_code == 422


def test_orchestrated_api_rejects_hybrid_with_doi():
    """Hybrid 不允许静默丢弃 DOI 条件。"""

    response = client.post(
        "/search/orchestrated",
        json={
            "query": "spectrogram",
            "doi": "10.1234/example",
            "strategy": "hybrid",
        },
    )

    assert response.status_code == 422


def test_orchestrated_api_rejects_invalid_limit():
    """检索数量必须符合范围约束。"""

    response = client.post(
        "/search/orchestrated",
        json={
            "query": "spectrogram",
            "limit": 0,
        },
    )

    assert response.status_code == 422


def test_orchestrated_api_rejects_invalid_strategy():
    """未知检索策略不能被自动接受。"""

    response = client.post(
        "/search/orchestrated",
        json={
            "query": "spectrogram",
            "strategy": "vector",
        },
    )

    assert response.status_code == 422