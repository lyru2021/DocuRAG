"""维护科研 Agent 可调用工具的显式白名单。"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel


class UnknownToolError(ValueError):
    """模型请求了未注册的工具。"""


class DuplicateToolError(ValueError):
    """工具名称重复注册。"""


@dataclass(frozen=True)
class RegisteredTool:
    """描述工具名称、参数模型及受控执行函数。"""

    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[[BaseModel], Any]


class ToolRegistry:
    """只允许访问显式注册的工具，不执行动态代码。"""

    def __init__(self):
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, tool: RegisteredTool) -> None:
        """注册工具并拒绝重复名称。"""

        if not tool.name or not tool.name.strip():
            raise ValueError("tool name must not be blank")

        if tool.name in self._tools:
            raise DuplicateToolError(
                f"duplicate tool: {tool.name}"
            )

        self._tools[tool.name] = tool

    def get(self, name: str) -> RegisteredTool:
        """仅从白名单中查找工具。"""

        tool = self._tools.get(name)

        if tool is None:
            raise UnknownToolError(
                f"unknown tool: {name}"
            )

        return tool

    def names(self) -> list[str]:
        """返回已注册工具的稳定名称列表。"""

        return sorted(self._tools)

    def definitions(self) -> list[dict]:
        """生成可供 LLM Provider 使用的工具描述。"""

        definitions = []

        for name in self.names():
            tool = self._tools[name]

            definitions.append({
                "type": "function",
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.args_model.model_json_schema(),
            })

        return definitions