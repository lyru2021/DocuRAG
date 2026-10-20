"""验证科研工作流补检、二次事实提取与证据复核的完整执行。"""

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


def make_response(facts):
    """构造一次确定性的模型事实提取响应。"""

    return LLMResponse(
        response_type="final_answer",
        content=json.dumps(
            {"facts": facts},
            ensure_ascii=False,
        ),
        provider="mock",
        model="mock-function-calling",
        usage=LLMUsage(
            input_tokens=50,
            output_tokens=20,
            total_tokens=70,
        ),
    )


def make_executor():
    """模拟初检和补检返回不同的真实结构 Chunk。"""

    registry = ToolRegistry()

    def handler(args):
        """根据检索阶段返回不同证据。"""

        if args.query == "detection":
            return [{
                "document_id": args.document_id,
                "chunk_id": args.document_id * 100 + 1,
                "title": f"Paper {args.document_id}",
                "page_start": 1,
                "page_end": 1,
                "content": "This paper investigates detection.",
            }]

        return [{
            "document_id": args.document_id,
            "chunk_id": args.document_id * 100 + 2,
            "title": f"Paper {args.document_id}",
            "page_start": 2,
            "page_end": 2,
            "content": (
                "The proposed transformer model "
                "uses spectrogram features."
            ),
        }]

    registry.register(
        RegisteredTool(
            name="search_chunks",
            description="Search research evidence",
            args_model=SearchChunksArgs,
            handler=handler,
        )
    )

    return ToolExecutor(
        registry,
        max_calls=5,
    )


def test_full_graph_rechecks_new_evidence():
    """完整工作流应二次提取新事实并更新证据覆盖度。"""

    # 第一次模型调用没有提取到可信事实。
    first_response = make_response([])

    # 第二次模型调用引用补检新增的 Chunk。
    second_response = make_response([
        {
            "document_id": 31,
            "chunk_id": 3102,
            "field": "method",
            "claim": "The paper uses a transformer model.",
            "quote": "transformer model",
            "page_start": 2,
            "page_end": 2,
        }
    ])

    llm = MockLLMAdapter([
        first_response,
        second_response,
    ])

    extractor = FactExtractor(llm)

    graph = build_research_graph(
        executor=make_executor(),
        fact_extractor=extractor,
        enable_supplement=True,
    )

    result = graph.invoke(
        initial_research_state(QUESTION)
    )

    # 整个工作流最多一轮补充检索。
    assert result["supplementary_searches"] == 1
    assert result["tool_calls"] <= 5

    # 初检和补检分别触发一次模型提取。
    assert len(llm.calls) == 2

    # 补检生成的新 Chunk 应进入增量证据集合。
    assert any(
        item["document_id"] == 31
        and item["chunk_id"] == 3102
        for item in result["supplementary_new_evidence"]
    )

    # 第二次提取的事实应通过真实原文校验。
    assert any(
        item["status"] == "quote_verified"
        and item["fact"]["chunk_id"] == 3102
        for item in result["fact_verifications"]
    )

    # 证据复核应识别论文31的方法字段已有真实引文。
    missing = result["evidence_judgement"]["missing_fields"]

    assert "method" not in missing["31"]

    # 其他字段仍缺少引文，不能直接产生完整结论。
    assert not result["evidence_judgement"][
        "sufficient_quote_coverage"
    ]

    # 复核以后不能再次进入补充检索。
    steps = [
        item["step"]
        for item in result["steps"]
    ]

    assert steps.count("supplement") == 1
    assert steps.count("evidence_recheck") == 1
    assert steps[-1] == "answer"

    # 两次提取的模型用量应累计。
    assert result["extraction_usage"]["total_tokens"] == 140

    assert result["answer"] == "未找到充分证据"