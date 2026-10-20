"""验证科研 Agent 工具参数的安全边界。"""

import pytest
from pydantic import ValidationError

from app.agent.tool_schemas import (
    GetEvidenceArgs,
    SearchChunksArgs,
    SearchPapersArgs,
    ToolCall,
)


def test_search_papers_accepts_doi():
    """DOI 可作为独立元数据过滤条件。"""

    args = SearchPapersArgs(
        doi="10.1234/example"
    )

    assert args.doi == "10.1234/example"
    assert args.limit == 5


def test_search_papers_requires_filter():
    """无条件元数据查询应拒绝。"""

    with pytest.raises(ValidationError):
        SearchPapersArgs()


def test_search_chunks_rejects_blank_query():
    """空白关键词不可执行。"""

    with pytest.raises(ValidationError):
        SearchChunksArgs(query="   ")


def test_search_chunks_rejects_unknown_mode():
    """模型不能自行发明检索模式。"""

    with pytest.raises(ValidationError):
        SearchChunksArgs(
            query="spectrogram",
            mode="python",
        )


def test_search_chunks_rejects_extra_arguments():
    """未知字段不能进入后端工具。"""

    with pytest.raises(ValidationError):
        SearchChunksArgs.model_validate({
            "query": "graph",
            "shell_command": "rm -rf /",
        })


def test_search_chunks_enforces_limit():
    """模型不能无限扩大检索结果数量。"""

    with pytest.raises(ValidationError):
        SearchChunksArgs(
            query="graph",
            limit=10000,
        )


def test_get_evidence_requires_real_identifiers():
    """证据工具必须使用合法的数据库 ID 参数。"""

    with pytest.raises(ValidationError):
        GetEvidenceArgs(
            document_id=31,
            chunk_id=-1,
        )


def test_get_evidence_rejects_injected_content():
    """模型不能把自己生成的文本作为数据库证据传入。"""

    with pytest.raises(ValidationError):
        GetEvidenceArgs.model_validate({
            "document_id": 31,
            "chunk_id": 101,
            "content": "fabricated evidence",
        })


def test_tool_call_can_represent_unknown_tool():
    """未知名称应交给工具注册表进行安全拒绝。"""

    call = ToolCall(
        call_id="call_001",
        name="execute_python",
        arguments={"code": "print(1)"},
    )

    assert call.name == "execute_python"