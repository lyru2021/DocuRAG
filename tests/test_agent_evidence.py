"""验证 Agent 只接受完整、合法且可定位的工具证据。"""

from app.agent.evidence import collect_evidence
from app.agent.tool_executor import ToolExecutionResult


def make_result(
    *,
    name="search_chunks",
    status="success",
    output=None,
):
    """构造测试用工具执行记录。"""

    return ToolExecutionResult(
        call_id="call_1",
        name=name,
        status=status,
        output=output,
        elapsed_ms=1.0,
    )


def make_evidence(chunk_id=101):
    """创建字段齐全的模拟数据库证据。"""

    return {
        "document_id": 31,
        "chunk_id": chunk_id,
        "title": "Audio Deepfake Detection",
        "page_start": 3,
        "page_end": 4,
        "content": "Spectrogram features are useful.",
    }


def test_collects_successful_chunk_evidence():
    """成功的 Chunk 检索结果可以进入证据列表。"""

    results = [
        make_result(output=[make_evidence()])
    ]

    evidence = collect_evidence(results)

    assert len(evidence) == 1
    assert evidence[0].document_id == 31
    assert evidence[0].chunk_id == 101


def test_collects_exact_evidence():
    """精确证据工具返回的单条记录可以进入列表。"""

    results = [
        make_result(
            name="get_evidence",
            output=make_evidence(),
        )
    ]

    evidence = collect_evidence(results)

    assert len(evidence) == 1
    assert evidence[0].page_start == 3


def test_ignores_failed_tool_results():
    """失败的工具调用不得贡献证据。"""

    results = [
        make_result(
            status="execution_error",
            output=[make_evidence()],
        )
    ]

    assert collect_evidence(results) == []


def test_ignores_incomplete_evidence():
    """缺少真实 Chunk ID 或页码的结果必须被忽略。"""

    incomplete = make_evidence()
    incomplete.pop("chunk_id")

    results = [
        make_result(output=[incomplete])
    ]

    assert collect_evidence(results) == []


def test_deduplicates_evidence():
    """同一 Document 和 Chunk 不得重复返回。"""

    results = [
        make_result(output=[
            make_evidence(),
            make_evidence(),
        ])
    ]

    evidence = collect_evidence(results)

    assert len(evidence) == 1


def test_enforces_evidence_count_limit():
    """模型调用多个工具也不能无限增加证据数量。"""

    results = [
        make_result(output=[
            make_evidence(chunk_id=101),
            make_evidence(chunk_id=102),
            make_evidence(chunk_id=103),
        ])
    ]

    evidence = collect_evidence(
        results,
        max_evidence=2,
    )

    assert len(evidence) == 2