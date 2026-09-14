from pathlib import Path
from datetime import datetime
import json


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
        raise SystemExit(
            f"Invalid JSON in {path}: {exc}"
        )


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
# MAIN PROGRAM
# -----------------------------

def main() -> None:
    profile = load_json(PROFILE_PATH)
    settings = load_json(SETTINGS_PATH)

    log_path = Path(settings["log_path"])

    log_event("CORE INITIALIZED", log_path)

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
            log_event("CORE SHUTDOWN", log_path)
            print("\nARIA: Goodbye, Beau.")
            break

        if not command:
            continue

        log_event(f"USER: {command}", log_path)

        if command.lower() in {"exit", "quit"}:
            log_event("CORE SHUTDOWN", log_path)
            print("ARIA: Goodbye, Beau.")
            break

        if command.lower() == "hello":
            response = "Hello, Beau."

        else:
            response = f"I heard you say: {command}"

        print(f"ARIA: {response}")
        log_event(f"ARIA: {response}", log_path)


if __name__ == "__main__":
    main()