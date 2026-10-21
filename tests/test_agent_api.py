"""验证科研 Agent HTTP 路由、请求校验及模型依赖替换。"""

from app.api.agent import get_llm_adapter
from app.agent.llm_adapter import LLMResponse
from app.agent.mock_llm import MockLLMAdapter


def test_agent_query_returns_mock_response(client):
    """默认 Mock Provider 可以完成 HTTP 请求。"""

    response = client.post(
        "/agent/query",
        json={"question": "Find papers about spectrograms"},
    )

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "completed"
    assert data["llm_calls"] == 1
    assert data["tool_calls"] == 0
    assert "Mock LLM" in data["answer"]


def test_agent_query_rejects_blank_question(client):
    """空字符串不得进入 Agent。"""

    response = client.post(
        "/agent/query",
        json={"question": ""},
    )

    assert response.status_code == 422


def test_agent_query_supports_llm_override(client):
    """测试可通过 FastAPI 依赖注入替换模型。"""

    from app.main import app

    app.dependency_overrides[get_llm_adapter] = lambda: MockLLMAdapter([
        LLMResponse(
            response_type="final_answer",
            content="This is a test answer.",
            provider="mock",
            model="mock-function-calling",
        )
    ])

    try:
        response = client.post(
            "/agent/query",
            json={"question": "Test"},
        )

        assert response.status_code == 200
        assert response.json()["answer"] == "This is a test answer."
    finally:
        app.dependency_overrides.pop(get_llm_adapter, None)


def test_agent_query_response_contains_usage(client):
    """HTTP 响应必须包含模型调用统计。"""

    response = client.post(
        "/agent/query",
        json={"question": "Find a paper"},
    )

    assert response.status_code == 200

    data = response.json()

    assert "input_tokens" in data
    assert "output_tokens" in data
    assert "total_tokens" in data
    assert "tools" in data


def test_agent_query_executes_tool_through_http(
    client,
    db_session,
):
    """验证 HTTP 接口能够完成模型工具调用与数据库证据查询。"""

    from app.main import app
    from app.agent.llm_adapter import LLMResponse
    from app.agent.mock_llm import MockLLMAdapter
    from app.agent.tool_schemas import ToolCall
    from app.api.agent import get_llm_adapter
    from app.models.document import Document, Chunk

    document = Document(
        title="Agent Integration Paper",
        filename="agent_integration.pdf",
        parse_status="parsed",
    )
    db_session.add(document)
    db_session.flush()

    content = "Spectrogram features support audio deepfake detection."

    chunk = Chunk(
        document_id=document.id,
        chunk_index=0,
        content=content,
        start_char=0,
        end_char=len(content),
        page_start=2,
        page_end=2,
    )
    db_session.add(chunk)
    db_session.commit()

    mock = MockLLMAdapter([
        LLMResponse(
            response_type="tool_calls",
            tool_calls=[
                ToolCall(
                    call_id="call_search_1",
                    name="search_chunks",
                    arguments={
                        "query": "Spectrogram",
                        "mode": "literal",
                        "document_id": document.id,
                    },
                )
            ],
            provider="mock",
            model="mock-function-calling",
        ),
        LLMResponse(
            response_type="final_answer",
            content="The paper discusses spectrogram features.",
            provider="mock",
            model="mock-function-calling",
        ),
    ])

    app.dependency_overrides[get_llm_adapter] = lambda: mock

    try:
        response = client.post(
            "/agent/query",
            json={
                "question": "Find spectrogram evidence"
            },
        )

        assert response.status_code == 200

        data = response.json()

        assert data["status"] == "completed"
        assert data["llm_calls"] == 2
        assert data["tool_calls"] == 1
        assert data["tools"][0]["name"] == "search_chunks"
        assert data["tools"][0]["status"] == "success"

        # 第二次模型调用应收到第一次工具执行的真实结果。
        messages = mock.calls[1]["messages"]

        tool_messages = [
            message
            for message in messages
            if message.role == "tool"
        ]

        assert len(tool_messages) == 1

        import json

        tool_output = json.loads(tool_messages[0].content)

        assert tool_output["status"] == "success"
        assert tool_output["output"][0]["document_id"] == document.id
        assert tool_output["output"][0]["chunk_id"] == chunk.id
        assert tool_output["output"][0]["content"] == content
        assert tool_output["output"][0]["page_start"] == 2

    finally:
        app.dependency_overrides.pop(
            get_llm_adapter,
            None,
        )


def test_agent_http_request_id_reaches_tool_logs(
    client,
    db_session,
    caplog,
):
    """验证 HTTP 请求 ID 能传播到 Agent 工具执行日志。"""

    import json
    import logging

    from app.main import app
    from app.agent.llm_adapter import LLMResponse
    from app.agent.mock_llm import MockLLMAdapter
    from app.agent.tool_schemas import ToolCall
    from app.api.agent import get_llm_adapter
    from app.models.document import Document, Chunk

    # 创建测试论文，避免使用真实私人论文。
    document = Document(
        title="Trace Integration Paper",
        filename="trace_integration.pdf",
        parse_status="parsed",
    )
    db_session.add(document)
    db_session.flush()

    content = "Traceable spectrogram evidence for audio detection."

    chunk = Chunk(
        document_id=document.id,
        chunk_index=0,
        content=content,
        start_char=0,
        end_char=len(content),
        page_start=1,
        page_end=1,
    )
    db_session.add(chunk)
    db_session.commit()

    # 第一次模型响应要求调用工具，第二次生成最终答案。
    mock = MockLLMAdapter([
        LLMResponse(
            response_type="tool_calls",
            tool_calls=[
                ToolCall(
                    call_id="trace-tool-001",
                    name="search_chunks",
                    arguments={
                        "query": "Traceable",
                        "mode": "literal",
                        "document_id": document.id,
                    },
                )
            ],
            provider="mock",
            model="mock-function-calling",
        ),
        LLMResponse(
            response_type="final_answer",
            content="Trace integration verified.",
            provider="mock",
            model="mock-function-calling",
        ),
    ])

    app.dependency_overrides[get_llm_adapter] = lambda: mock

    try:
        with caplog.at_level(logging.INFO):
            response = client.post(
                "/agent/query",
                headers={
                    "X-Request-ID": "research-trace-001",
                },
                json={
                    "question": "Find traceable evidence",
                },
            )

        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == (
            "research-trace-001"
        )

        data = response.json()
        assert data["tool_calls"] == 1
        assert data["tools"][0]["status"] == "success"

        # 提取本次请求相关的结构化日志。
        http_logs = []
        tool_logs = []

        for record in caplog.records:
            if record.name not in {
                "docurag.http",
                "docurag.agent.tools",
            }:
                continue

            payload = json.loads(record.message)

            if record.name == "docurag.http":
                http_logs.append(payload)
            else:
                tool_logs.append(payload)

        # HTTP 和工具日志应共享同一个 request_id。
        assert any(
            item["request_id"] == "research-trace-001"
            and item["status_code"] == 200
            for item in http_logs
        )

        assert any(
            item["request_id"] == "research-trace-001"
            and item["tool_name"] == "search_chunks"
            and item["status"] == "success"
            for item in tool_logs
        )

        # 日志不应泄露论文内容或工具查询参数。
        log_text = "\n".join(
            record.message
            for record in caplog.records
            if record.name in {
                "docurag.http",
                "docurag.agent.tools",
            }
        )

        assert content not in log_text
        assert "Traceable" not in log_text

    finally:
        app.dependency_overrides.pop(
            get_llm_adapter,
            None,
        )


def create_agent_evidence(db_session):
    """创建具有真实页码和原文的 Agent 测试证据。"""

    from app.models.document import Chunk, Document

    document = Document(
        title="Evidence Audit Paper",
        filename="evidence_audit.pdf",
        parse_status="parsed",
    )
    db_session.add(document)
    db_session.flush()

    content = (
        "Spectrogram representations are used "
        "for audio deepfake detection."
    )

    chunk = Chunk(
        document_id=document.id,
        chunk_index=0,
        content=content,
        start_char=0,
        end_char=len(content),
        page_start=4,
        page_end=5,
    )

    db_session.add(chunk)
    db_session.commit()

    return document, chunk

def test_agent_http_evidence_matches_postgres(client, db_session):
    """HTTP 证据必须与 PostgreSQL 中的 Chunk 完全一致。"""

    from app.main import app
    from app.api.agent import get_llm_adapter
    from app.agent.llm_adapter import LLMResponse
    from app.agent.mock_llm import MockLLMAdapter
    from app.agent.tool_schemas import ToolCall

    document, chunk = create_agent_evidence(db_session)

    mock = MockLLMAdapter([
        LLMResponse(
            response_type="tool_calls",
            tool_calls=[
                ToolCall(
                    call_id="evidence_1",
                    name="get_evidence",
                    arguments={
                        "document_id": document.id,
                        "chunk_id": chunk.id,
                    },
                )
            ],
            provider="mock",
            model="mock-function-calling",
        ),
        LLMResponse(
            response_type="final_answer",
            content="The paper uses spectrograms.",
            provider="mock",
            model="mock-function-calling",
        ),
    ])

    app.dependency_overrides[get_llm_adapter] = lambda: mock

    try:
        response = client.post(
            "/agent/query",
            json={"question": "Find the original evidence"},
        )
    finally:
        app.dependency_overrides.pop(get_llm_adapter, None)

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "completed"
    assert len(data["evidence"]) == 1

    evidence = data["evidence"][0]

    assert evidence["document_id"] == document.id
    assert evidence["chunk_id"] == chunk.id
    assert evidence["title"] == document.title
    assert evidence["page_start"] == chunk.page_start
    assert evidence["page_end"] == chunk.page_end
    assert evidence["content"] == chunk.content


def test_agent_http_deduplicates_evidence(client, db_session):
    """同一数据库 Chunk 多次返回也只能出现一次。"""

    from app.main import app
    from app.api.agent import get_llm_adapter
    from app.agent.llm_adapter import LLMResponse
    from app.agent.mock_llm import MockLLMAdapter
    from app.agent.tool_schemas import ToolCall

    document, chunk = create_agent_evidence(db_session)

    mock = MockLLMAdapter([
        LLMResponse(
            response_type="tool_calls",
            tool_calls=[
                ToolCall(
                    call_id="first",
                    name="get_evidence",
                    arguments={
                        "document_id": document.id,
                        "chunk_id": chunk.id,
                    },
                ),
                ToolCall(
                    call_id="second",
                    name="get_evidence",
                    arguments={
                        "document_id": document.id,
                        "chunk_id": chunk.id,
                    },
                ),
            ],
            provider="mock",
            model="mock-function-calling",
        ),
        LLMResponse(
            response_type="final_answer",
            content="Evidence found.",
            provider="mock",
            model="mock-function-calling",
        ),
    ])

    app.dependency_overrides[get_llm_adapter] = lambda: mock

    try:
        response = client.post(
            "/agent/query",
            json={"question": "Find evidence"},
        )
    finally:
        app.dependency_overrides.pop(get_llm_adapter, None)

    assert response.status_code == 200

    data = response.json()

    assert data["tool_calls"] == 2
    assert len(data["evidence"]) == 1
    assert data["evidence"][0]["chunk_id"] == chunk.id


def test_agent_http_does_not_trust_fabricated_citations(client):
    """模型仅在回答文本中声明的引用不算数据库证据。"""

    from app.main import app
    from app.api.agent import get_llm_adapter
    from app.agent.llm_adapter import LLMResponse
    from app.agent.mock_llm import MockLLMAdapter

    mock = MockLLMAdapter([
        LLMResponse(
            response_type="final_answer",
            content=(
                "According to document 999999, "
                "chunk 888888, page 42, this is proven."
            ),
            provider="mock",
            model="mock-function-calling",
        )
    ])

    app.dependency_overrides[get_llm_adapter] = lambda: mock

    try:
        response = client.post(
            "/agent/query",
            json={"question": "Find supporting evidence"},
        )
    finally:
        app.dependency_overrides.pop(get_llm_adapter, None)

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "completed"
    assert data["evidence"] == []


def test_agent_http_rejects_missing_evidence(client):
    """不存在的数据库 Chunk 不得成为有效来源。"""

    from app.main import app
    from app.api.agent import get_llm_adapter
    from app.agent.llm_adapter import LLMResponse
    from app.agent.mock_llm import MockLLMAdapter
    from app.agent.tool_schemas import ToolCall

    mock = MockLLMAdapter([
        LLMResponse(
            response_type="tool_calls",
            tool_calls=[
                ToolCall(
                    call_id="missing_1",
                    name="get_evidence",
                    arguments={
                        "document_id": 999999999,
                        "chunk_id": 999999999,
                    },
                )
            ],
            provider="mock",
            model="mock-function-calling",
        ),
        LLMResponse(
            response_type="final_answer",
            content="No verified evidence was found.",
            provider="mock",
            model="mock-function-calling",
        ),
    ])

    app.dependency_overrides[get_llm_adapter] = lambda: mock

    try:
        response = client.post(
            "/agent/query",
            json={"question": "Get missing evidence"},
        )
    finally:
        app.dependency_overrides.pop(get_llm_adapter, None)

    assert response.status_code == 200

    data = response.json()

    assert data["tool_calls"] == 1
    assert data["tools"][0]["status"] == "execution_error"
    assert data["tools"][0]["error_type"] == "EvidenceNotFoundError"
    assert data["evidence"] == []