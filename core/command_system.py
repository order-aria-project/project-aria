from collections.abc import Callable
from typing import Any


class CommandSystem:
    """Routes user commands to registered command handlers."""

    def __init__(self) -> None:
        self._commands: dict[str, Callable[..., str]] = {}

    def register(
        self,
        name: str,
        handler: Callable[..., str],
    ) -> None:
        """Register an exact command."""
        self._commands[name.lower()] = handler

    def execute(self, command: str) -> str:
        """Find and execute a registered command."""
        normalized = command.strip().lower()

        if not normalized:
            return ""

        # Exact command.
        handler = self._commands.get(normalized)

        if handler is not None:
            try:
                return handler()
            except Exception as exc:
                return f"I couldn't complete that command: {exc}"

        return f"I don't know how to do '{command}'."