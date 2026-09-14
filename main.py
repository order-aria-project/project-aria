from pathlib import Path
from datetime import datetime
import json

from core.event_bus import EventBus
from core.events import (
    USER_COMMAND,
    ARIA_RESPONSE,
    CORE_STARTED,
    CORE_SHUTDOWN,
)
from core.command_system import CommandSystem
from core.commands import hello, system_status


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
    """Load a JSON configuration file safely."""
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    except FileNotFoundError:
        raise SystemExit(f"Configuration file not found: {path}")

    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}")


# -----------------------------
# MISSION LOGGER
# -----------------------------

def log_event(message: str, log_path: Path) -> None:
    """Write an event to ARIA's Mission Log."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    log_path.parent.mkdir(parents=True, exist_ok=True)

    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(f"[{timestamp}] {message}\n")


# -----------------------------
# EVENT HANDLERS
# -----------------------------

def handle_user_command(command: str, log_path: Path) -> None:
    log_event(f"USER: {command}", log_path)


def handle_aria_response(response: str, log_path: Path) -> None:
    log_event(f"ARIA: {response}", log_path)


def handle_core_started(log_path: Path) -> None:
    log_event("CORE INITIALIZED", log_path)


def handle_core_shutdown(log_path: Path) -> None:
    log_event("CORE SHUTDOWN", log_path)


# -----------------------------
# MAIN PROGRAM
# -----------------------------

def main() -> None:
    profile = load_json(PROFILE_PATH)
    settings = load_json(SETTINGS_PATH)

    log_path = Path(settings["log_path"])

    # Create ARIA's event system.
    event_bus = EventBus()

    # Create ARIA's command system.
    command_system = CommandSystem()

    # Register commands.
    command_system.register("hello", hello)
    command_system.register("system status", system_status)

    # Connect event handlers.
    event_bus.subscribe(
        USER_COMMAND,
        lambda command: handle_user_command(command, log_path)
    )

    event_bus.subscribe(
        ARIA_RESPONSE,
        lambda response: handle_aria_response(response, log_path)
    )

    event_bus.subscribe(
        CORE_STARTED,
        lambda: handle_core_started(log_path)
    )

    event_bus.subscribe(
        CORE_SHUTDOWN,
        lambda: handle_core_shutdown(log_path)
    )

    # Announce startup.
    event_bus.publish(CORE_STARTED)

    print("=" * 50)
    print(f"{profile['name']} — {profile['version']}")
    print(f"Meaning: {profile['meaning']}")
    print(f"Owner: {profile['owner']}")
    print(f"Build: {profile['build']}")
    print("=" * 50)
    print("CORE ONLINE")
    print("=" * 50)

    while True:
        try:
            command = input("You: ").strip()

        except (KeyboardInterrupt, EOFError):
            event_bus.publish(CORE_SHUTDOWN)
            print("\nARIA: Goodbye, Beau.")
            break

        if not command:
            continue

        event_bus.publish(
            USER_COMMAND,
            command=command
        )

        if command.lower() in {"exit", "quit"}:
            event_bus.publish(CORE_SHUTDOWN)
            print("ARIA: Goodbye, Beau.")
            break

        response = command_system.execute(command)

        print(f"ARIA: {response}")

        event_bus.publish(
            ARIA_RESPONSE,
            response=response
        )


if __name__ == "__main__":
    main()