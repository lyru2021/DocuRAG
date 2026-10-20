"""验证 DeepSeek Provider 配置，不发送真实网络请求。"""

from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from app.api import agent as agent_api


def make_settings(key="test-key"):
    """创建测试专用的 DeepSeek 配置。"""

    return SimpleNamespace(
        LLM_PROVIDER="deepseek",
        DEEPSEEK_API_KEY=(
            SecretStr(key) if key is not None else None
        ),
        DEEPSEEK_MODEL="deepseek-flash",
        DEEPSEEK_TIMEOUT_SECONDS=30.0,
    )


def test_deepseek_missing_key_is_rejected(monkeypatch):
    """缺少 API Key 时不应调用模型。"""

    monkeypatch.setattr(
        agent_api,
        "get_settings",
        lambda: make_settings(key=None),
    )

    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        agent_api.get_llm_adapter()


def test_deepseek_uses_correct_configuration(monkeypatch):
    """验证模型名称、Provider 和 API 地址。"""

    captured = {}

    def fake_adapter(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(
        agent_api,
        "get_settings",
        lambda: make_settings(),
    )

    monkeypatch.setattr(
        agent_api,
        "OpenAIAdapter",
        fake_adapter,
    )

    agent_api.get_llm_adapter()

    assert captured["provider"] == "deepseek"
    assert captured["model"] == "deepseek-flash"
    assert captured["base_url"] == "https://api.deepseek.com"
    assert captured["timeout"] == 30.0


def test_deepseek_blank_key_is_rejected(monkeypatch):
    """空白 API Key 也不能启用真实模型。"""

    monkeypatch.setattr(
        agent_api,
        "get_settings",
        lambda: make_settings(key="   "),
    )

    with pytest.raises(RuntimeError, match="blank"):
        agent_api.get_llm_adapter()