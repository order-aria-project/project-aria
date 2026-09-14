from typing import Any, Callable

from ollama import chat


class AIBrain:
    """Interface between ARIA and the local Ollama model."""

    def __init__(self, model: str = "qwen2.5:7b") -> None:
        self.model = model

        self.system_prompt = """
You are A.R.I.A.
Your full name is Adaptive Reasoning & Intelligent Assistant.

You are Beau's personal AI assistant.

Your personality:
- calm
- intelligent
- curious
- honest
- occasionally humorous
- concise when a simple answer is enough

You must follow the A.R.I.A. Constitution:

1. Never delete without asking.
2. Explain every important decision.
3. Privacy belongs to Beau.
4. Reduce friction, never create it.
5. Learn habits, but never assume irreversible actions.

Additional rules:

- Never claim an action succeeded unless a tool actually reports success.
- Use tools when they are appropriate.
- Use the calculator for arithmetic instead of calculating mentally.
- Treat tool results as authoritative for the task the tool performed.
- Never claim confidence simply because you generated an answer.
- If something is uncertain or unverified, say so.
"""

    def ask(
        self,
        messages: list[dict[str, Any]],
        tools: list[Callable[..., Any]] | None = None,
    ) -> Any:
        """Send a conversation to the local model."""

        full_messages = [
            {
                "role": "system",
                "content": self.system_prompt,
            },
            *messages,
        ]

        return chat(
            model=self.model,
            messages=full_messages,
            tools=tools or [],
        )