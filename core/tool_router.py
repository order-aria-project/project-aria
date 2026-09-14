from collections.abc import Callable
from typing import Any


class ToolRouter:
    """Controls which tools ARIA is allowed to execute."""

    def __init__(self) -> None:
        self._tools: dict[str, Callable[..., Any]] = {}

    def register(
        self,
        name: str,
        function: Callable[..., Any],
    ) -> None:
        """Register an approved ARIA tool."""
        if name in self._tools:
            raise ValueError(f"Tool already registered: {name}")

        self._tools[name] = function

    def get_tools(self) -> list[Callable[..., Any]]:
        """Return approved tools."""
        return list(self._tools.values())

    def get_tool(self, name: str) -> Callable[..., Any] | None:
        """Retrieve a tool by name."""
        return self._tools.get(name)

    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> str:
        """Execute a registered tool safely."""
        tool = self.get_tool(name)

        if tool is None:
            return f"Tool '{name}' is not available."

        try:
            result = tool(**arguments)
            return str(result)
        except Exception as exc:
            return f"Tool execution failed: {exc}"