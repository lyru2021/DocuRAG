"""验证 Agent 模型配置选择，不发送真实 API 请求。"""

from types import SimpleNamespace

import pytest
from pydantic import SecretStr, ValidationError

from app.agent.mock_llm import MockLLMAdapter
from app.api import agent as agent_api
from app.core.config import Settings


def fake_settings(
    *,
    provider="mock",
    key=None,
):
    """构造不读取真实环境密钥的测试配置。"""

    return SimpleNamespace(
        LLM_PROVIDER=provider,
        OPENAI_API_KEY=(
            SecretStr(key)
            if key is not None
            else None
        ),
        OPENAI_MODEL="test-model",
        OPENAI_TIMEOUT_SECONDS=5.0,
    )


def test_default_provider_is_mock(monkeypatch):
    """Mock 模式不得创建真实 OpenAI 客户端。"""

    monkeypatch.setattr(
        agent_api,
        "get_settings",
        lambda: fake_settings(),
    )

    def forbidden_adapter(**kwargs):
        raise AssertionError(
            "OpenAI client must not be created"
        )

    monkeypatch.setattr(
        agent_api,
        "OpenAIAdapter",
        forbidden_adapter,
    )

    adapter = agent_api.get_llm_adapter()

    assert isinstance(adapter, MockLLMAdapter)


def test_openai_without_key_is_rejected(monkeypatch):
    """启用真实 Provider 却缺少密钥时必须报错。"""

    monkeypatch.setattr(
        agent_api,
        "get_settings",
        lambda: fake_settings(
            provider="openai",
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="OPENAI_API_KEY is required",
    ):
        agent_api.get_llm_adapter()


def test_openai_provider_receives_configuration(monkeypatch):
    """真实 Provider 配置必须正确传递，且不联网。"""

    captured = {}

    def fake_openai_adapter(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(
        agent_api,
        "get_settings",
        lambda: fake_settings(
            provider="openai",
            key="test-secret-only",
        ),
    )

    monkeypatch.setattr(
        agent_api,
        "OpenAIAdapter",
        fake_openai_adapter,
    )

    adapter = agent_api.get_llm_adapter()

    assert adapter is not None
    assert captured["model"] == "test-model"
    assert captured["api_key"] == "test-secret-only"
    assert captured["timeout"] == 5.0


def test_invalid_provider_configuration_is_rejected():
    """配置层应拒绝不支持的 Provider。"""

    with pytest.raises(ValidationError):
        Settings(
            DATABASE_URL="sqlite:///test.db",
            LLM_PROVIDER="execute_python",
            _env_file=None,
        )