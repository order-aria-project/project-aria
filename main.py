from pathlib import Path
from datetime import datetime
import json
from typing import Any

from core.ai_brain import AIBrain
from core.app_registry import AppRegistry
from core.tool_router import ToolRouter
from core.event_bus import EventBus
from core.events import (
    USER_COMMAND,
    ARIA_RESPONSE,
    CORE_STARTED,
    CORE_SHUTDOWN,
)
from core.conversation_manager import ConversationManager

from tools.application_tools import ApplicationTools
from tools.calculator_tools import calculate
from tools.system_tools import (
    get_cpu_usage,
    get_ram_usage,
    get_gpu_info,
    get_disk_space,
    get_battery,
    get_running_applications,
    get_system_status,
)


# -----------------------------
# ARIA PATHS
# -----------------------------

PROJECT_ROOT = Path(__file__).resolve().parent

PROFILE_PATH = PROJECT_ROOT / "core" / "aria_profile.json"
SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.json"


# -----------------------------
# CONFIGURATION
# -----------------------------

def load_json(path: Path) -> dict:
    """Load a JSON file safely."""
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    except FileNotFoundError:
        raise SystemExit(
            f"Configuration file not found: {path}"
        )

    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"Invalid JSON in {path}: {exc}"
        )


# -----------------------------
# MISSION LOGGER
# -----------------------------

def log_event(message: str, log_path: Path) -> None:
    """Write an event to ARIA's Mission Log."""
    timestamp = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    log_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with log_path.open(
        "a",
        encoding="utf-8",
    ) as log_file:
        log_file.write(
            f"[{timestamp}] {message}\n"
        )


# -----------------------------
# MAIN PROGRAM
# -----------------------------

def main() -> None:
    profile = load_json(PROFILE_PATH)
    settings = load_json(SETTINGS_PATH)

    log_path = Path(
        settings["log_path"]
    )

    # -------------------------
    # Event Bus
    # -------------------------

    event_bus = EventBus()

    event_bus.subscribe(
        USER_COMMAND,
        lambda command: log_event(
            f"USER: {command}",
            log_path,
        ),
    )

    event_bus.subscribe(
        ARIA_RESPONSE,
        lambda response: log_event(
            f"ARIA: {response}",
            log_path,
        ),
    )

    event_bus.subscribe(
        CORE_STARTED,
        lambda: log_event(
            "CORE INITIALIZED",
            log_path,
        ),
    )

    event_bus.subscribe(
        CORE_SHUTDOWN,
        lambda: log_event(
            "CORE SHUTDOWN",
            log_path,
        ),
    )

    # -------------------------
    # Application Registry
    # -------------------------

    registry_path = (
        PROJECT_ROOT
        / "config"
        / "applications.json"
    )

    app_registry = AppRegistry(
        registry_path
    )

    # -------------------------
    # Application Tools
    # -------------------------

    application_tools = ApplicationTools(
        app_registry
    )

    # -------------------------
    # Tool Router
    # -------------------------

    tool_router = ToolRouter()

    tool_router.register(
        "launch",
        application_tools.launch,
    )

    tool_router.register(
        "calculate",
        calculate,
    )

    tool_router.register(
        "get_cpu_usage",
        get_cpu_usage,
    )

    tool_router.register(
        "get_ram_usage",
        get_ram_usage,
    )

    tool_router.register(
        "get_gpu_info",
        get_gpu_info,
    )

    tool_router.register(
        "get_disk_space",
        get_disk_space,
    )

    tool_router.register(
        "get_battery",
        get_battery,
    )

    tool_router.register(
        "get_running_applications",
        get_running_applications,
    )

    tool_router.register(
        "get_system_status",
        get_system_status,
    )

    # -------------------------
    # AI Brain
    # -------------------------

    brain = AIBrain()

    # -------------------------
    # Conversation Manager
    # -------------------------

    conversation = ConversationManager(
        max_messages=20
    )

    # -------------------------
    # Startup
    # -------------------------

    event_bus.publish(
        CORE_STARTED
    )

    print("=" * 60)
    print(
        f"{profile['name']} — "
        f"{profile['version']}"
    )
    print(
        f"Meaning: "
        f"{profile['meaning']}"
    )
    print(
        f"Owner: "
        f"{profile['owner']}"
    )
    print(
        f"Build: "
        f"{profile['build']}"
    )
    print("=" * 60)
    print("CORE ONLINE")
    print("AI ONLINE")
    print("TOOLS ONLINE")
    print("MEMORY ONLINE")
    print("SYSTEM AWARENESS ONLINE")
    print("=" * 60)

    # -------------------------
    # Main Conversation Loop
    # -------------------------

    while True:
        try:
            user_input = input(
                "You: "
            ).strip()

        except (
            KeyboardInterrupt,
            EOFError,
        ):
            event_bus.publish(
                CORE_SHUTDOWN
            )

            print(
                "\nARIA: Goodbye, Beau."
            )

            break

        if not user_input:
            continue

        if user_input.lower() in {
            "exit",
            "quit",
        }:
            event_bus.publish(
                CORE_SHUTDOWN
            )

            print(
                "ARIA: Goodbye, Beau."
            )

            break

        # -------------------------
        # Store User Message
        # -------------------------

        event_bus.publish(
            USER_COMMAND,
            command=user_input,
        )

        conversation.add_user_message(
            user_input
        )

        try:
            # -------------------------
            # First AI Request
            # -------------------------

            response = brain.ask(
                conversation.get_messages(),
                tools=tool_router.get_tools(),
            )

            assistant_content = (
                response.message.content or ""
            )

            tool_calls = (
                response.message.tool_calls
            )

            # -------------------------
            # No Tool Required
            # -------------------------

            if not tool_calls:
                conversation.add_assistant_message(
                    assistant_content
                )

                print(
                    f"ARIA: "
                    f"{assistant_content}"
                )

                event_bus.publish(
                    ARIA_RESPONSE,
                    response=assistant_content,
                )

                continue

            # -------------------------
            # Record Assistant Tool Call
            # -------------------------

            conversation.add_assistant_message(
                assistant_content,
                tool_calls=[
                    {
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        }
                    }
                    for call in tool_calls
                ],
            )

            # -------------------------
            # Execute Tools
            # -------------------------

            for call in tool_calls:
                tool_name = (
                    call.function.name
                )

                arguments = (
                    call.function.arguments
                )

                log_event(
                    f"TOOL REQUEST: "
                    f"{tool_name} "
                    f"{arguments}",
                    log_path,
                )

                print(
                    f"[TOOL] "
                    f"{tool_name}"
                    f"({arguments})"
                )

                result = (
                    tool_router.execute(
                        tool_name,
                        arguments,
                    )
                )

                log_event(
                    f"TOOL RESULT: "
                    f"{result}",
                    log_path,
                )

                print(
                    f"[TOOL RESULT] "
                    f"{result}"
                )

                conversation.add_tool_result(
                    result
                )

            # -------------------------
            # Final AI Response
            # -------------------------

            final_response = brain.ask(
                conversation.get_messages()
            )

            final_content = (
                final_response.message.content
                or ""
            )

            conversation.add_assistant_message(
                final_content
            )

            print(
                f"ARIA: "
                f"{final_content}"
            )

            event_bus.publish(
                ARIA_RESPONSE,
                response=final_content,
            )

        except Exception as exc:
            error_message = (
                "I encountered an error while "
                f"processing that: {exc}"
            )

            print(
                f"ARIA: "
                f"{error_message}"
            )

            log_event(
                f"ERROR: {exc}",
                log_path,
            )

            event_bus.publish(
                ARIA_RESPONSE,
                response=error_message,
            )


if __name__ == "__main__":
    main()