from pathlib import Path

from core.ai_brain import AIBrain
from core.app_registry import AppRegistry
from core.tool_router import ToolRouter
from tools.application_tools import ApplicationTools
from tools.calculator_tools import calculate


def main() -> None:
    registry = AppRegistry(
        Path("A:/Core/Project/config/applications.json")
    )

    application_tools = ApplicationTools(registry)

    tool_router = ToolRouter()

    tool_router.register(
    "launch",
    application_tools.launch,
    )

    tool_router.register(
    "calculate",
    calculate,
    )

    brain = AIBrain()

    print("=" * 60)
    print("ARIA TOOL-CALLING TEST")
    print("Type 'exit' to stop.")
    print("=" * 60)

    while True:
        message = input("You: ").strip()

        if not message:
            continue

        if message.lower() == "exit":
            break

        # First response: Qwen decides whether it needs a tool.
        response, tool_calls = brain.ask(
            message,
            tools=tool_router.get_tools(),
        )

        # No tool needed.
        if not tool_calls:
            print(f"ARIA: {response}")
            print()
            continue

        # Build the conversation that will be sent back to Qwen.
        messages = [
            {
                "role": "user",
                "content": message,
            }
        ]

        # Record Qwen's tool-call response.
        messages.append(
            {
                "role": "assistant",
                "content": response or "",
                "tool_calls": [
                    {
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        }
                    }
                    for call in tool_calls
                ],
            }
        )

        # Execute every requested tool.
        for call in tool_calls:
            tool_name = call.function.name
            arguments = call.function.arguments

            print(
                f"[TOOL REQUEST] "
                f"{tool_name}({arguments})"
            )

            tool = tool_router.get_tool(tool_name)

            if tool is None:
                result = f"Unknown tool: {tool_name}"
            else:
                try:
                    result = tool(**arguments)
                except Exception as exc:
                    result = f"Tool execution failed: {exc}"

            print(f"[TOOL RESULT] {result}")

            messages.append(
                {
                    "role": "tool",
                    "content": result,
                }
            )

        # Ask Qwen to produce the final natural response.
        final_response, _ = brain.ask_with_messages(
            messages
        )

        print(f"ARIA: {final_response}")
        print()


if __name__ == "__main__":
    main()