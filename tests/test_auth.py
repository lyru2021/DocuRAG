
"""验证 DocuRAG API Key 鉴权及健康检查边界。"""

from types import SimpleNamespace

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.auth import require_api_key


def make_auth_settings(
    *,
    enabled: bool = True,
    api_key: str | None = "test-secret-key",
    app_env: str = "test",
):
    """创建不依赖真实环境密钥的测试配置。"""

    return SimpleNamespace(
        AUTH_ENABLED=enabled,
        DOCURAG_API_KEY=(
            SecretStr(api_key) if api_key is not None else None
        ),
        APP_ENV=app_env,
    )


def test_missing_api_key_is_rejected(monkeypatch):
    """开启鉴权时，无密钥请求必须被拒绝。"""

    from app.main import app

    monkeypatch.setattr(
        "app.core.auth.get_settings",
        lambda: make_auth_settings(),
    )

    with TestClient(app) as client:
        response = client.post(
            "/agent/query",
            json={"question": "Find evidence"},
        )

    assert response.status_code == 401


def test_wrong_api_key_is_rejected(monkeypatch):
    """错误 API Key 不得进入业务逻辑。"""

    from app.main import app

    monkeypatch.setattr(
        "app.core.auth.get_settings",
        lambda: make_auth_settings(),
    )

    with TestClient(app) as client:
        response = client.post(
            "/agent/query",
            headers={"X-API-Key": "wrong-key"},
            json={"question": "Find evidence"},
        )

    assert response.status_code == 401


def test_valid_api_key_is_accepted(client, monkeypatch):
    """正确 API Key 可以进入现有 Agent 接口。"""

    monkeypatch.setattr(
        "app.core.auth.get_settings",
        lambda: make_auth_settings(),
    )

    response = client.post(
        "/agent/query",
        headers={"X-API-Key": "test-secret-key"},
        json={"question": "Find spectrogram papers"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_health_remains_public(monkeypatch):
    """健康检查必须允许匿名访问。"""

    from app.main import app

    monkeypatch.setattr(
        "app.core.auth.get_settings",
        lambda: make_auth_settings(),
    )

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200


def test_missing_server_key_fails_closed(monkeypatch):
    """启用鉴权但缺少服务端密钥时不得放行。"""

    from app.main import app

    monkeypatch.setattr(
        "app.core.auth.get_settings",
        lambda: make_auth_settings(api_key=None),
    )

    with TestClient(app) as client:
        response = client.post(
            "/agent/query",
            headers={"X-API-Key": "some-key"},
            json={"question": "Find evidence"},
        )

    assert response.status_code == 503


def test_disabling_auth_in_production_is_forbidden(monkeypatch):
    """生产环境不得通过配置关闭鉴权。"""

    from app.main import app

    monkeypatch.setattr(
        "app.core.auth.get_settings",
        lambda: make_auth_settings(
            enabled=False,
            app_env="production",
        ),
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/agent/query",
            json={"question": "Find evidence"},
        )

    assert response.status_code == 500
