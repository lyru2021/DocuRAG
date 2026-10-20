"""验证 LangGraph 事实提取节点的结果传递与安全降级。"""

import json

from app.agent.fact_extractor import FactExtractor
from app.agent.llm_adapter import LLMResponse, LLMUsage
from app.agent.mock_llm import MockLLMAdapter
from app.agent.research_graph import (
    build_research_graph,
    initial_research_state,
)
from app.agent.tool_executor import ToolExecutor
from app.agent.tool_registry import RegisteredTool, ToolRegistry
from app.agent.tool_schemas import SearchChunksArgs


QUESTION = (
    "Compare document 31 and document 32 "
    "for deepfake detection"
)


def make_evidence(document_id):
    """创建两篇论文各自的候选证据。"""

    return {
        "document_id": document_id,
        "chunk_id": document_id + 100,
        "title": f"Paper {document_id}",
        "page_start": 2,
        "page_end": 2,
        "content": (
            "The proposed transformer model "
            "uses spectrogram features."
        ),
    }


def make_fact(quote="transformer model"):
    """构造模型提出的待核验事实。"""

    return {
        "document_id": 31,
        "chunk_id": 131,
        "field": "method",
        "claim": "The study uses a transformer model.",
        "quote": quote,
        "page_start": 2,
        "page_end": 2,
    }


def make_graph(extractor=None, handler=None):
    """构造共享预算的 Mock 检索工作流。"""

    registry = ToolRegistry()

    if handler is None:
        handler = lambda args: [
            make_evidence(args.document_id)
        ]

    registry.register(
        RegisteredTool(
            name="search_chunks",
            description="Search stored evidence",
            args_model=SearchChunksArgs,
            handler=handler,
        )
    )

    executor = ToolExecutor(registry, max_calls=5)

    return build_research_graph(
        executor=executor,
        fact_extractor=extractor,
    )


def mock_extractor(facts):
    """构造确定性、零网络费用的事实提取器。"""

    llm = MockLLMAdapter([
        LLMResponse(
            response_type="final_answer",
            content=json.dumps(
                {"facts": facts},
                ensure_ascii=False,
            ),
            provider="mock",
            model="mock-function-calling",
            usage=LLMUsage(
                input_tokens=80,
                output_tokens=20,
                total_tokens=100,
            ),
        )
    ])

    return FactExtractor(llm), llm


def test_graph_verifies_extracted_quote():
    """真实原文子串通过验证并进入 Graph State。"""

    extractor, llm = mock_extractor([make_fact()])

    result = make_graph(extractor).invoke(
        initial_research_state(QUESTION)
    )

    # 初始检索两篇论文，Evidence Judge 发现其余字段缺失，
    # 因此还会执行最多一轮补检，但总预算不能超过 5 次。
    assert result["tool_calls"] == 5

    assert result["supplementary_searches"] == 1

    assert result["tool_calls"] <= 5

    assert [
        step["step"]
        for step in result["steps"]
        if step["step"].startswith("retrieve:")
    ] == [
        "retrieve:T1",
        "retrieve:T2",
    ]
    assert len(result["fact_verifications"]) == 1
    assert (
        result["fact_verifications"][0]["status"]
        == "quote_verified"
    )
    assert result["extraction_usage"]["total_tokens"] == 100
    assert len(llm.calls) == 1


def test_graph_rejects_fabricated_quote():
    """编造引文不能变成受支持的矩阵字段。"""

    extractor, _ = mock_extractor([
        make_fact(quote="The model achieved 100% accuracy.")
    ])

    result = make_graph(extractor).invoke(
        initial_research_state(QUESTION)
    )

    assert (
        result["fact_verifications"][0]["status"]
        == "quote_mismatch"
    )

    assert all(
        row["method"]["status"] != "supported"
        for row in result["evidence_matrix"]
    )


def test_empty_evidence_skips_fact_extraction():
    """没有数据库证据时不调用模型。"""

    extractor = FactExtractor(MockLLMAdapter([]))

    result = make_graph(
        extractor,
        handler=lambda args: [],
    ).invoke(initial_research_state(QUESTION))

    assert result["fact_verifications"] == []
    assert result["extraction_usage"] == {}

    assert any(
        step["step"] == "extract_facts"
        and step["status"] == "skipped"
        for step in result["steps"]
    )


def test_model_failure_does_not_destroy_evidence():
    """模型故障不会丢弃已获取的真实证据。"""

    extractor = FactExtractor(MockLLMAdapter([]))

    result = make_graph(extractor).invoke(
        initial_research_state(QUESTION)
    )

    assert len(result["evidence"]) == 2
    assert result["fact_verifications"] == []

    assert any(
        step["step"] == "extract_facts"
        and step["status"] == "failed"
        for step in result["steps"]
    )


def test_graph_without_extractor_remains_compatible():
    """未启用事实提取时保留原来的节点顺序。"""

    result = make_graph().invoke(
        initial_research_state(QUESTION)
    )

    steps = [
        step["step"]
        for step in result["steps"]
    ]

    assert steps[:6] == [
        "plan",
        "retrieve:T1",
        "retrieve:T2",
        "classify_fields",
        "matrix",
        "evidence_judge",
    ]

    assert steps[-1] == "answer"

    assert "supplement" in steps

    assert result["supplementary_searches"] == 1
    assert result["tool_calls"] <= 5

    # 未注入 FactExtractor，不能生成已核验事实。
    assert result["fact_verifications"] == []