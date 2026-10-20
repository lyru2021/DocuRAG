"""验证 LLM 事实提取、引用核验和非法输出处理。"""

import json

import pytest

from app.agent.fact_extractor import (
    FactExtractor,
    FactExtractionError,
)
from app.agent.llm_adapter import LLMResponse, LLMUsage
from app.agent.mock_llm import MockLLMAdapter


def make_evidence():
    """构造具有真实来源字段的测试 Chunk。"""

    return {
        "document_id": 31,
        "chunk_id": 47,
        "title": "Test Paper",
        "page_start": 1,
        "page_end": 1,
        "content": (
            "The study evaluates models utilizing "
            "Log-Mel spectrograms."
        ),
    }


def make_fact(**overrides):
    """创建待验证的模型输出事实。"""

    fact = {
        "document_id": 31,
        "chunk_id": 47,
        "field": "method",
        "claim": "The study evaluates Log-Mel models.",
        "quote": "models utilizing Log-Mel spectrograms",
        "page_start": 1,
        "page_end": 1,
    }
    fact.update(overrides)
    return fact


def make_mock(payload):
    """提供确定性 LLM JSON 响应。"""

    content = (
        payload
        if isinstance(payload, str)
        else json.dumps(payload, ensure_ascii=False)
    )

    return MockLLMAdapter([
        LLMResponse(
            response_type="final_answer",
            content=content,
            provider="mock",
            model="mock-function-calling",
            usage=LLMUsage(
                input_tokens=100,
                output_tokens=50,
                total_tokens=150,
            ),
        )
    ])


def test_extracts_verified_quote():
    """合法模型事实必须经过后端原文匹配。"""

    llm = make_mock({
        "facts": [make_fact()]
    })

    result = FactExtractor(llm).extract(
        "What methods were evaluated?",
        [make_evidence()],
    )

    assert len(result.verifications) == 1
    assert result.verifications[0].status == "quote_verified"
    assert result.total_tokens == 150
    assert llm.calls[0]["tools"] == []


def test_rejects_fabricated_quote():
    """虚构引文不会通过原文校验。"""

    llm = make_mock({
        "facts": [
            make_fact(quote="The model achieved 100% accuracy")
        ]
    })

    result = FactExtractor(llm).extract(
        "What are the results?",
        [make_evidence()],
    )

    assert result.verifications[0].status == "quote_mismatch"


def test_rejects_unknown_chunk():
    """模型不能引用本轮没有检索到的 Chunk。"""

    llm = make_mock({
        "facts": [make_fact(chunk_id=999999)]
    })

    result = FactExtractor(llm).extract(
        "Find the methods",
        [make_evidence()],
    )

    assert result.verifications[0].status == "evidence_not_found"


def test_rejects_invalid_json():
    """非法 JSON 必须明确失败。"""

    llm = make_mock("This is not JSON.")

    with pytest.raises(
        FactExtractionError,
        match="invalid fact JSON",
    ):
        FactExtractor(llm).extract(
            "Find the methods",
            [make_evidence()],
        )


def test_rejects_excessive_facts():
    """模型不能突破事实数量上限。"""

    llm = make_mock({
        "facts": [make_fact(), make_fact()]
    })

    with pytest.raises(FactExtractionError):
        FactExtractor(llm, max_facts=1).extract(
            "Find methods",
            [make_evidence()],
        )


def test_empty_evidence_skips_llm():
    """没有候选证据时，不应浪费真实 API 调用。"""

    llm = MockLLMAdapter([])

    result = FactExtractor(llm).extract(
        "Find the methods",
        [],
    )

    assert result.verifications == []
    assert llm.calls == []