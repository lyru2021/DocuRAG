from fastapi.testclient import TestClient   #FastAPI 提供的测试客户端，可以向应用模拟 HTTP 请求
from app.main import app

client = TestClient(app)

def test_health_status_code():
    response = client.get("/health")
    assert response.status_code == 200  #如果条件为真，测试继续；如果条件为假，就触发 AssertionError


def test_health_response_body():
    response = client.get("/health")
    assert response.json() == {"status": "ok"}


def test_docs_available():
    response = client.get("/docs")
    assert response.status_code == 200
