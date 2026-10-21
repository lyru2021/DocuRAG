"""验证 Agent 工具执行日志的关联标识与安全性。"""

import json
import logging

from pydantic import BaseModel

from app.agent.tool_executor import ToolExecutor
from app.agent.tool_registry import RegisteredTool, ToolRegistry
from app.agent.tool_schemas import ToolCall
from app.core.request_logging import request_id_context


class EchoArgs(BaseModel):
    """测试工具的参数模型。"""

    value: str

def make_executor() -> ToolExecutor:
    """创建包含受控测试工具的执行器。"""

    registry = ToolRegistry()

    registry.register(
        RegisteredTool(
            name="echo",
            description="Return the supplied test value.",
            args_model=EchoArgs,
            handler=lambda args: {"value": args.value},
        )
    )

    return ToolExecutor(registry, max_calls=5)


def test_tool_log_contains_request_id(caplog):
    """工具执行日志应携带当前请求标识。"""

    executor = make_executor()
    token = request_id_context.set("research-123")

    try:
        with caplog.at_level(
            logging.INFO,
            logger="docurag.agent.tools",
        ):
            result = executor.execute(
                ToolCall(
                    call_id="call-1",
                    name="echo",
                    arguments={"value": "hello"},
                )
            )
    finally:
        request_id_context.reset(token)

    records = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "docurag.agent.tools"
    ]

    assert result.status == "success"
    assert len(records) == 1
    assert records[0]["request_id"] == "research-123"
    assert records[0]["tool_name"] == "echo"
    assert records[0]["duration_ms"] >= 0


def test_tool_log_does_not_expose_arguments(caplog):
    """工具日志不得泄露参数和返回正文。"""

    executor = make_executor()
    secret = "PRIVATE_PAPER_CONTENT_123"

    with caplog.at_level(
        logging.INFO,
        logger="docurag.agent.tools",
    ):
        result = executor.execute(
            ToolCall(
                call_id="call-2",
                name="echo",
                arguments={"value": secret},
            )
        )

    assert result.status == "success"

    messages = "\n".join(
        record.message
        for record in caplog.records
        if record.name == "docurag.agent.tools"
    )

    assert secret not in messages
    assert "arguments" not in messages
    assert "output" not in messages


def test_invalid_tool_call_produces_log(caplog):
    """非法工具参数也应留下审计记录。"""

    executor = make_executor()

    with caplog.at_level(
        logging.INFO,
        logger="docurag.agent.tools",
    ):
        result = executor.execute(
            ToolCall(
                call_id="call-3",
                name="echo",
                arguments={},
            )
        )

    records = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "docurag.agent.tools"
    ]

    assert result.status == "invalid_arguments"
    assert records[-1]["status"] == "invalid_arguments"
    assert records[-1]["error_type"] == "ValidationError"
