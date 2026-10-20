"""验证并执行白名单工具，记录状态和限制输出大小。"""

import json
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Literal

from pydantic import ValidationError

from app.agent.tool_registry import (
    ToolRegistry,
    UnknownToolError,
)
from app.agent.tool_schemas import ToolCall


@dataclass(frozen=True)
class ToolExecutionResult:
    """统一表示一次工具调用的实际执行结果。"""

    call_id: str
    name: str
    status: Literal[
        "success",
        "unknown_tool",
        "invalid_arguments",
        "limit_exceeded",
        "execution_error",
        "output_too_large",
        "duplicate_call_id",
    ]
    output: Any | None
    elapsed_ms: float
    error_type: str | None = None


class ToolExecutor:
    """仅运行注册表中的工具，限制单次对话调用数量。"""

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        max_calls: int = 5,
        max_output_chars: int = 10000,
    ):
        if max_calls < 1:
            raise ValueError("max_calls must be positive")

        if max_output_chars < 1:
            raise ValueError(
                "max_output_chars must be positive"
            )

        self.registry = registry
        self.max_calls = max_calls
        self.max_output_chars = max_output_chars
        self.call_count = 0
        self._seen_call_ids: set[str] = set()

    def execute(self, call: ToolCall) -> ToolExecutionResult:
        """验证工具名称、参数、预算，再执行注册的 Handler。"""

        start = perf_counter()

        if self.call_count >= self.max_calls:
            return self._result(
                call,
                "limit_exceeded",
                start,
            )

        # 重复调用不会再次执行 Handler。
        if call.call_id in self._seen_call_ids:
            return self._result(
                call,
                "duplicate_call_id",
                start,
            )

        # 首次调用无论是否合法，都占用调用预算。
        self._seen_call_ids.add(call.call_id)
        self.call_count += 1

        try:
            tool = self.registry.get(call.name)
        except UnknownToolError as exc:
            return self._result(
                call,
                "unknown_tool",
                start,
                error_type=type(exc).__name__,
            )

        try:
            arguments = tool.args_model.model_validate(
                call.arguments
            )
        except ValidationError as exc:
            return self._result(
                call,
                "invalid_arguments",
                start,
                error_type=type(exc).__name__,
            )

        try:
            output = tool.handler(arguments)
        except Exception as exc:
            return self._result(
                call,
                "execution_error",
                start,
                error_type=type(exc).__name__,
            )

        try:
            serialized = json.dumps(
                output,
                ensure_ascii=False,
                default=self._serialize,
            )
        except (TypeError, ValueError) as exc:
            return self._result(
                call,
                "execution_error",
                start,
                error_type=type(exc).__name__,
            )

        # 不截断 JSON，以免生成无法解析的工具响应。
        if len(serialized) > self.max_output_chars:
            return self._result(
                call,
                "output_too_large",
                start,
            )

        return self._result(
            call,
            "success",
            start,
            output=json.loads(serialized),
        )

    @staticmethod
    def _serialize(value: Any) -> Any:
        """允许工具返回 Pydantic 对象，但拒绝未知对象类型。"""

        from pydantic import BaseModel

        if isinstance(value, BaseModel):
            return value.model_dump(mode="json")

        raise TypeError(
            f"unsupported tool output type: {type(value).__name__}"
        )

    @staticmethod
    def _result(
        call: ToolCall,
        status: str,
        start: float,
        *,
        output: Any | None = None,
        error_type: str | None = None,
    ) -> ToolExecutionResult:
        """生成统一执行记录。"""

        return ToolExecutionResult(
            call_id=call.call_id,
            name=call.name,
            status=status,
            output=output,
            elapsed_ms=(perf_counter() - start) * 1000,
            error_type=error_type,
        )