"""使用脚本化 Mock LLM 验证 Agent 对真实 PostgreSQL 的工具调用。"""

import json
from pathlib import Path

from dotenv import dotenv_values

from app.agent.llm_adapter import LLMResponse
from app.agent.mock_llm import MockLLMAdapter
from app.agent.paper_tools import build_paper_tool_registry
from app.agent.research_agent import ResearchAgent
from app.agent.tool_executor import ToolExecutor
from app.agent.tool_schemas import ToolCall
from app.agent.tool_db import make_production_tool_session
from app.core.request_logging import request_id_context

# 使用独立、只读的数据库会话工厂。
# 注意：这里通过本地 Python 连接数据库，不改变 Docker 服务。
session_factory = make_production_tool_session(
    statement_timeout_ms=3000
)

mock = MockLLMAdapter([
    LLMResponse(
        response_type="tool_calls",
        tool_calls=[
            ToolCall(
                call_id="day13-demo-search-call",
                name="search_chunks",
                arguments={
                    "query": "spectrogram",
                    "mode": "literal",
                    "document_id": 1,
                    "limit": 5,
                },
            ),
        ],
        provider="mock",
        model="mock-function-calling",
    ),
    LLMResponse(
        response_type="final_answer",
        content=(
            "Synthetic demonstration only. "
            "The retrieved paper describes spectrogram representations."
        ),
        provider="mock",
        model="mock-function-calling",
    ),
])

agent = ResearchAgent(
    llm=mock,
    executor=ToolExecutor(
        build_paper_tool_registry(session_factory),
        max_calls=5,
        max_output_chars=10000,
    ),
    max_llm_calls=6,
)

# 独立脚本没有 HTTP Middleware，显式注入演示请求 ID。
token = request_id_context.set("day13-agent-tool-demo")

try:
    result = agent.run(
        "Find spectrogram evidence in document 1."
    )
finally:
    request_id_context.reset(token)

assert result.status == "completed", result.status
assert result.llm_calls == 2, result.llm_calls
assert result.tool_calls == 1, result.tool_calls
assert len(result.tool_results) == 1

tool = result.tool_results[0]

assert tool.name == "search_chunks"
assert tool.status == "success", tool.error_type

# 第二次 Mock 调用收到真实数据库工具返回的消息。
tool_messages = [
    message
    for message in mock.calls[1]["messages"]
    if message.role == "tool"
]

assert len(tool_messages) == 1

tool_output = json.loads(tool_messages[0].content)

assert tool_output["status"] == "success"

matches = tool_output["output"]

assert matches, "The PostgreSQL search returned no matches."

assert any(
    item["document_id"] == 1
    and item["chunk_id"] == 1
    and item["page_start"] == 1
    and "spectrogram" in item["content"].lower()
    for item in matches
), "The expected evidence was not found."

summary = {
    "status": result.status,
    "llm_provider": "mock",
    "llm_calls": result.llm_calls,
    "tool_calls": result.tool_calls,
    "tool_name": tool.name,
    "tool_status": tool.status,
    "document_ids": [
        item["document_id"] for item in matches
    ],
    "chunk_ids": [
        item["chunk_id"] for item in matches
    ],
    "pages": [
        [item["page_start"], item["page_end"]]
        for item in matches
    ],
    "request_id": "day13-agent-tool-demo",
    "answer": result.answer,
}

print(json.dumps(summary, ensure_ascii=False, indent=2))
print("\nDay 13F Agent PostgreSQL tool chain: PASS")