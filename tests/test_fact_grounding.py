"""验证科研事实引用的数据库定位、页码及原文真实性。"""

import pytest
from pydantic import ValidationError

from app.agent.fact_grounding import (
    ProposedFact,
    verify_proposed_fact,
    verify_proposed_facts,
)


def make_evidence():
    """构造与真实 Chunk 结构一致的测试证据。"""

    return {
        "document_id": 31,
        "chunk_id": 47,
        "title": "Audio Deepfake Detection",
        "page_start": 1,
        "page_end": 1,
        "content": (
            "The study evaluates models utilizing "
            "Log-Mel spectrograms."
        ),
    }


def make_fact(**overrides):
    """构造模型提出的待核验事实。"""

    data = {
        "document_id": 31,
        "chunk_id": 47,
        "field": "method",
        "claim": "论文使用 Log-Mel 频谱图模型。",
        "quote": "models utilizing Log-Mel spectrograms",
        "page_start": 1,
        "page_end": 1,
    }

    data.update(overrides)

    return ProposedFact(**data)


def test_exact_quote_is_verified():
    """原文引用完全一致时通过引用校验。"""

    result = verify_proposed_fact(
        make_fact(),
        [make_evidence()],
    )

    assert result.status == "quote_verified"


def test_unknown_chunk_is_rejected():
    """不存在于本轮检索中的 Chunk 不能作为来源。"""

    result = verify_proposed_fact(
        make_fact(chunk_id=999999),
        [make_evidence()],
    )

    assert result.status == "evidence_not_found"


def test_wrong_document_is_rejected():
    """不同论文的 Chunk 不得被错误关联。"""

    result = verify_proposed_fact(
        make_fact(document_id=32),
        [make_evidence()],
    )

    assert result.status == "evidence_not_found"


def test_wrong_page_is_rejected():
    """模型不能修改引用页码。"""

    result = verify_proposed_fact(
        make_fact(page_start=5, page_end=5),
        [make_evidence()],
    )

    assert result.status == "page_mismatch"


def test_fabricated_quote_is_rejected():
    """补写或改写后的文字不属于原文引用。"""

    result = verify_proposed_fact(
        make_fact(
            quote="models utilizing Log-Mel spectrograms achieve 100% accuracy"
        ),
        [make_evidence()],
    )

    assert result.status == "quote_mismatch"


def test_invalid_and_excessive_facts_are_rejected():
    """非法字段及超过数量上限的事实均不得通过。"""

    with pytest.raises(ValidationError):
        make_fact(field="execute_python")

    with pytest.raises(ValueError, match="too many"):
        verify_proposed_facts(
            [make_fact(), make_fact()],
            [make_evidence()],
            max_facts=1,
        )