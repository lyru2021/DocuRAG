"""应用健康检查和 Swagger 文档入口测试。"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_status_code():
    response = client.get("/health")
    assert response.status_code == 200


def test_health_response_body():
    response = client.get("/health")
    assert response.json() == {"status": "ok"}


def test_docs_available():
    response = client.get("/docs")
    assert response.status_code == 200
