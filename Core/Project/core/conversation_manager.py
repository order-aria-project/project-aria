from typing import Any


class ConversationManager:
    """Manages ARIA's current conversation context."""

    def __init__(self, max_messages: int = 20) -> None:
        self.max_messages = max_messages
        self._messages: list[dict[str, Any]] = []

    def add_user_message(self, content: str) -> None:
        """Add a user message to the conversation."""
        self._messages.append(
            {
                "role": "user",
                "content": content,
            }
        )

        self._trim()

    def add_assistant_message(
        self,
        content: str,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> None:
        """Add an assistant message."""
        message: dict[str, Any] = {
            "role": "assistant",
            "content": content,
        }

        if tool_calls:
            message["tool_calls"] = tool_calls

        self._messages.append(message)

        self._trim()

    def add_tool_result(self, content: str) -> None:
        """Add a tool result to the conversation."""
        self._messages.append(
            {
                "role": "tool",
                "content": content,
            }
        )

        self._trim()

    def get_messages(self) -> list[dict[str, Any]]:
        """Return a copy of the current conversation."""
        return list(self._messages)

    def clear(self) -> None:
        """Clear the current conversation."""
        self._messages.clear()

    def _trim(self) -> None:
        """Keep only the most recent messages."""
        if len(self._messages) > self.max_messages:
            self._messages = self._messages[-self.max_messages:]