"""验证二次事实提取、结果保留及补检后的覆盖度复核。"""

import json

from app.agent.fact_extractor import FactExtractor
from app.agent.llm_adapter import LLMResponse, LLMUsage
from app.agent.mock_llm import MockLLMAdapter
from app.agent.research_graph import initial_research_state
from app.agent.research_recheck_node import (
    evidence_recheck_node,
    make_supplementary_fact_node,
)


QUESTION = (
    "Compare document 31 and document 32 "
    "for deepfake detection"
)


def make_evidence(chunk_id):
    """构造来自数据库的候选 Chunk。"""

    return {
        "document_id": 31,
        "chunk_id": chunk_id,
        "title": "Paper 31",
        "page_start": 2,
        "page_end": 2,
        "content": "The transformer model uses spectrogram features.",
    }


def make_fact(chunk_id):
    """构造与新增 Chunk 对应的模型事实。"""

    return {
        "document_id": 31,
        "chunk_id": chunk_id,
        "field": "method",
        "claim": "The paper uses a transformer model.",
        "quote": "transformer model",
        "page_start": 2,
        "page_end": 2,
    }


def make_extractor(facts):
    """创建返回固定 JSON 的零网络费用模型。"""

    llm = MockLLMAdapter([
        LLMResponse(
            response_type="final_answer",
            content=json.dumps({"facts": facts}),
            provider="mock",
            model="mock-function-calling",
            usage=LLMUsage(
                input_tokens=50,
                output_tokens=20,
                total_tokens=70,
            ),
        )
    ])
    return FactExtractor(llm), llm


def make_state():
    """创建包含初检和补检记录的测试状态。"""

    state = initial_research_state(QUESTION)

    state["retrieval_plan"] = [
        {
            "task_id": f"T{i}",
            "tool_name": "search_chunks",
            "arguments": {
                "document_id": document_id,
                "query": "detection",
                "mode": "literal",
                "limit": 5,
            },
            "purpose": "Research comparison",
        }
        for i, document_id in enumerate(
            [31, 32], start=1
        )
    ]

    return state


def test_second_extraction_verifies_new_chunk():
    """新增 Chunk 能生成新的引文核验记录。"""

    state = make_state()
    state["supplementary_new_evidence"] = [make_evidence(102)]

    extractor, llm = make_extractor([make_fact(102)])

    update = make_supplementary_fact_node(extractor)(state)

    assert len(update["fact_verifications"]) == 1
    assert (
        update["fact_verifications"][0]["status"]
        == "quote_verified"
    )
    assert len(llm.calls) == 1


def test_no_new_chunks_skips_llm():
    """重复检索已有 Chunk 不产生额外模型费用。"""

    state = make_state()

    extractor, llm = make_extractor([])

    update = make_supplementary_fact_node(extractor)(state)

    assert "fact_verifications" not in update
    assert len(llm.calls) == 0
    assert update["steps"][-1]["status"] == "skipped"


def test_old_verifications_are_preserved():
    """二次事实提取不得覆盖初次核验结果。"""

    state = make_state()

    extractor, _ = make_extractor([make_fact(101)])
    state["supplementary_new_evidence"] = [make_evidence(101)]

    state["fact_verifications"] = [
        {
            "status": "quote_verified",
            "reason": "Original quote found",
            "fact": make_fact(100),
        }
    ]

    update = make_supplementary_fact_node(extractor)(state)

    assert {
        item["fact"]["chunk_id"]
        for item in update["fact_verifications"]
    } == {100, 101}


def test_second_extraction_failure_preserves_state():
    """LLM 失败时不修改已有事实。"""

    state = make_state()
    state["supplementary_new_evidence"] = [make_evidence(102)]

    state["fact_verifications"] = [{
        "status": "quote_verified",
        "reason": "Original quote found",
        "fact": make_fact(100),
    }]

    extractor = FactExtractor(MockLLMAdapter([]))

    update = make_supplementary_fact_node(extractor)(state)

    assert "fact_verifications" not in update
    assert state["fact_verifications"][0]["fact"]["chunk_id"] == 100
    assert update["steps"][-1]["status"] == "failed"


def test_recheck_does_not_schedule_second_round():
    """二次 Judge 只能复核，不得规划另一轮补检。"""

    state = make_state()
    state["supplementary_searches"] = 1

    state["supplementary_tasks"] = [
        {
            "task_id": "S1",
            "tool_name": "search_chunks",
            "arguments": {
                "document_id": 31,
                "query": "results",
                "mode": "literal",
                "limit": 5,
            },
            "purpose": "Old supplementary task",
        }
    ]

    state["fact_verifications"] = [{
        "status": "quote_verified",
        "reason": "Exact quote found",
        "fact": make_fact(101),
    }]

    update = evidence_recheck_node(state)

    assert update["supplementary_tasks"] == []
    assert not update["evidence_judgement"][
        "sufficient_quote_coverage"
    ]

    assert "method" not in update[
        "evidence_judgement"
    ]["missing_fields"]["31"]

    assert update["steps"][-1]["step"] == "evidence_recheck"